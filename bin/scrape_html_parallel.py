#!/usr/bin/env python3
"""
scrape_html_parallel.py — Parallel runner for the 12 HTML/curl scrapers.

Replaces the inline heredoc wrapper in SKILL.md Step 3. Lives in bin/ so
cron sessions never need to write multi-line Python with nested for/if
blocks (which has failed in past runs due to leading-whitespace stripping).

Behavior:
- Spawns all 12 scrapers in parallel via subprocess.Popen
- Each scraper runs with --days 1.5 (36h cutoff, hard per spec)
- Per-scraper timeout: 180s (matches SKILL.md default)
- Stdout redirected to <site_id>_reviews.json in --out-dir
- stderr silenced (noisy Cloudflare/SSL warnings)
- Waits for all to finish, prints one summary line per scraper to stderr
- Returns exit 0 even if some scrapers fail (downstream merge is tolerant)

Usage:
    python3 scrape_html_parallel.py [--out-dir DIR] [--days 1.5] [--timeout 180]

Default --out-dir: $HERMES_KANBAN_WORKSPACE/YYYY/MM/YYYY-MM-DD  (the music-record path)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# (script_basename, site_id, mode) — mode is either:
#   "stdout"   scraper writes JSON to stdout (most of them)
#   "out_dir"  scraper takes --out-dir and writes its own file
#              (scrape_sea_of_tranquility is the only one; inconsistency
#              is preserved here so we don't fork another working tree)
SCRIPTS = [
    ("scrape_all_about_jazz",     "all_about_jazz",     "stdout"),
    ("scrape_dark_entries",       "dark_entries_be",    "stdout"),
    ("scrape_downbeat",           "downbeat",           "stdout"),
    ("scrape_free_jazz_blog",     "free_jazz_blog",     "stdout"),
    ("scrape_jazz_trail",         "jazz_trail",         "stdout"),
    ("scrape_mixmag_asia",        "mixmag_asia",        "stdout"),
    ("scrape_musique_machine",    "musique_machine",    "stdout"),
    ("scrape_resident_advisor",   "resident_advisor",   "stdout"),
    ("scrape_sea_of_tranquility", "sea_of_tranquility", "out_dir"),
    ("scrape_songlines",          "songlines",          "stdout"),
    ("scrape_squids_ear",         "squids_ear",         "stdout"),
    ("scrape_wild_city",          "wild_city",          "stdout"),
]


def default_out_dir() -> str:
    """<music-record>/2026/MM/YYYY-MM-DD unless HERMES_KANBAN_WORKSPACE is set."""
    ws = os.environ.get("HERMES_KANBAN_WORKSPACE", "/home/liyifan/music-record")
    now = datetime.now()
    return f"{ws}/2026/{now.strftime('%m')}/{now.strftime('%Y-%m-%d')}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parallel HTML scraper runner for music-daily-recs Step 3")
    p.add_argument("--out-dir", default=default_out_dir(),
                   help="Where to write <site_id>_reviews.json (default: $HERMES_KANBAN_WORKSPACE/2026/MM/YYYY-MM-DD)")
    p.add_argument("--days", default="1.5",
                   help="Cutoff in days passed to each scraper (default 1.5 = 36h, hard per spec)")
    p.add_argument("--timeout", type=int, default=180,
                   help="Per-scraper timeout in seconds (default 180)")
    p.add_argument("--bin-dir", default=os.path.expanduser("~/.local/bin"),
                   help="Where to find the scrape_*.py scripts (default ~/.local/bin)")
    p.add_argument("--max-parallel", type=int, default=12,
                   help="Max concurrent scrapers (default 12 = all at once)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    launched = []
    for script, site_id, mode in SCRIPTS:
        script_path = os.path.join(args.bin_dir, f"{script}.py")
        out_file = out_dir / f"{site_id}_reviews.json"
        cmd = [
            "timeout", str(args.timeout),
            "python3", script_path,
            "--days", str(args.days),
        ]
        if mode == "stdout":
            # Most scrapers: JSON on stdout, redirect to file. Truncate so a
            # re-run doesn't see stale content.
            try:
                fout = open(out_file, "w", buffering=1)  # line-buffered
            except OSError as e:
                print(f"  {site_id}: cannot open {out_file} ({e})", file=sys.stderr, flush=True)
                continue
            try:
                p = subprocess.Popen(cmd, stdout=fout, stderr=subprocess.DEVNULL)
                launched.append((p, site_id, out_file, fout, time.monotonic()))
                print(f"  launched {site_id} (pid {p.pid}) -> {out_file.name}", file=sys.stderr, flush=True)
            except OSError as e:
                fout.close()
                print(f"  {site_id}: Popen failed ({e})", file=sys.stderr, flush=True)
        elif mode == "out_dir":
            # scrape_sea_of_tranquility writes its own file; pass --out-dir,
            # swallow stdout (it's a log line, not JSON), capture stderr to
            # a sibling log file for debugging.
            cmd.extend(["--out-dir", str(out_dir)])
            log_file = out_dir / f"{site_id}_scrape.log"
            try:
                flog = open(log_file, "w", buffering=1)
            except OSError as e:
                print(f"  {site_id}: cannot open log {log_file} ({e})", file=sys.stderr, flush=True)
                continue
            try:
                p = subprocess.Popen(cmd, stdout=flog, stderr=flog)
                launched.append((p, site_id, out_file, flog, time.monotonic()))
                print(f"  launched {site_id} (pid {p.pid}) -> {out_file.name} (writes itself)", file=sys.stderr, flush=True)
            except OSError as e:
                flog.close()
                print(f"  {site_id}: Popen failed ({e})", file=sys.stderr, flush=True)

    # Wait for all, with a small grace period past timeout to allow cleanup.
    grace = 10
    deadline_per = args.timeout + grace
    print(f"\nWaiting on {len(launched)} scrapers (timeout {args.timeout}s each)...", file=sys.stderr, flush=True)

    for p, site_id, out_file, fout, t0 in launched:
        try:
            rc = p.wait(timeout=deadline_per - (time.monotonic() - t0))
        except subprocess.TimeoutExpired:
            p.kill()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            fout.close()
            print(f"  {site_id}: TIMEOUT after {deadline_per}s", file=sys.stderr, flush=True)
            continue
        finally:
            try:
                fout.close()
            except Exception:
                pass
        elapsed = int(time.monotonic() - t0)
        # Try to count items if the JSON is well-formed
        items = "?"
        try:
            with open(out_file) as f:
                data = json.load(f)
            if isinstance(data, list):
                items = len(data)
            elif isinstance(data, dict):
                items = len(data.get("items", []) or data.get("reviews", []))
        except (OSError, json.JSONDecodeError):
            items = "?"
        status = "ok" if rc == 0 else f"rc={rc}"
        print(f"  {site_id}: {status} items={items} elapsed={elapsed}s", file=sys.stderr, flush=True)

    print(f"\nDone. Output in: {out_dir}", file=sys.stderr, flush=True)
    # Don't fail the cron step on individual scraper errors — downstream
    # merge tolerates missing or empty _reviews.json files. Returning 0
    # lets the pipeline continue to Step 4 (merge) and Step 5 (swarm).
    return 0


if __name__ == "__main__":
    sys.exit(main())
