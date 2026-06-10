#!/usr/bin/env python3
"""
scrape_html_parallel.py — 并发运行所有 HTML scrape 脚本，合并为一个 JSON。

每个 scrape_*.py 作为子进程运行，stdout 捕获 JSON 结果。
所有结果在内存中合并，直接写出一个 html_reviews.json。

用法:
  python3 scrape_html_parallel.py --out-dir /path/to/date-dir
  python3 scrape_html_parallel.py --out-dir /path --days 1.5 --timeout 180
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = [
    ("scrape_all_about_jazz",        "all_about_jazz",           "stdout"),
    ("scrape_bandwagon_asia",        "bandwagon_asia",           "stdout"),
    ("scrape_dark_entries",          "dark_entries_be",          "stdout"),
    ("scrape_downbeat",              "downbeat",                 "stdout"),
    ("scrape_free_jazz_blog",        "free_jazz_blog",           "stdout"),
    ("scrape_hear65",                "hear65",                   "stdout"),
    ("scrape_jazz_trail",            "jazz_trail",               "stdout"),
    ("scrape_mixmag_asia",           "mixmag_asia",              "stdout"),
    ("scrape_musique_machine",       "musique_machine",          "stdout"),
    ("scrape_resident_advisor",      "resident_advisor",         "stdout"),
    ("scrape_roots_world",           "roots_world",              "stdout"),
    ("scrape_sea_of_tranquility",    "sea_of_tranquility",       "out_dir"),
    ("scrape_songlines",             "songlines",                "stdout"),
    ("scrape_squids_ear",            "squids_ear",               "stdout"),
    ("scrape_strangely_isolated_place", "strangely_isolated_place", "stdout"),
    ("scrape_truth_and_lies_music",  "truth_and_lies_music",     "stdout"),
    ("scrape_world_music_central",   "world_music_central",      "stdout"),
]


def default_out_dir() -> str:
    ws = os.environ.get("HERMES_KANBAN_WORKSPACE", "/home/liyifan/music-record")
    now = datetime.now()
    return f"{ws}/2026/{now.strftime('%m')}/{now.strftime('%Y-%m-%d')}"


def parse_args():
    p = argparse.ArgumentParser(description="并发 HTML 抓取 → 单个 JSON")
    p.add_argument("--out-dir", default=default_out_dir())
    p.add_argument("--days", default="1.5")
    p.add_argument("--timeout", type=int, default=180,
                   help="Per-scraper timeout (default 180s)")
    p.add_argument("--bin-dir", default=str(Path(__file__).resolve().parent))
    return p.parse_args()


def run_scraper(script, site_id, mode, bin_dir, out_dir, days, timeout):
    """Run one scraper subprocess, return (site_id, items_list, error_str)."""
    script_path = os.path.join(bin_dir, f"{script}.py")
    cmd = ["timeout", str(timeout), "python3", script_path, "--days", str(days)]

    if mode == "out_dir":
        cmd.extend(["--out-dir", str(out_dir)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        # sea_of_tranquility writes its own file — read it back
        out_file = Path(out_dir) / f"{site_id}_reviews.json"
        if out_file.exists() and out_file.stat().st_size > 5:
            try:
                data = json.loads(out_file.read_text())
                items = data.get("items", []) if isinstance(data, dict) else []
                return site_id, items, None
            except json.JSONDecodeError as e:
                return site_id, [], f"JSON parse error: {e}"
        return site_id, [], f"no output file (rc={result.returncode})"
    else:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        stdout = result.stdout.strip()
        if not stdout:
            stderr_tail = result.stderr.strip()[-200:] if result.stderr else ""
            return site_id, [], f"empty stdout (rc={result.returncode}) {stderr_tail}"
        try:
            data = json.loads(stdout)
            items = data.get("items", []) if isinstance(data, dict) else []
            return site_id, items, None
        except json.JSONDecodeError as e:
            return site_id, [], f"JSON parse error: {e}"


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"HTML: {len(SCRIPTS)} 脚本, timeout={args.timeout}s, days={args.days}",
          file=sys.stderr)

    # Run all scrapers concurrently via ThreadPoolExecutor
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_items = []
    errors = []
    t0 = time.monotonic()

    with ThreadPoolExecutor(max_workers=len(SCRIPTS)) as pool:
        futures = {
            pool.submit(run_scraper, script, site_id, mode,
                        args.bin_dir, str(out_dir), args.days, args.timeout): site_id
            for script, site_id, mode in SCRIPTS
        }
        for future in as_completed(futures):
            site_id = futures[future]
            try:
                sid, items, err = future.result()
                if err:
                    print(f"  {sid}: ❌ {err}", file=sys.stderr)
                    errors.append((sid, err))
                else:
                    print(f"  {sid}: ✅ {len(items)} items", file=sys.stderr)
                    all_items.extend(items)
            except Exception as e:
                print(f"  {site_id}: 💥 {e}", file=sys.stderr)
                errors.append((site_id, str(e)))

    elapsed = int(time.monotonic() - t0)
    all_items.sort(key=lambda r: r.get("pub_date") or "", reverse=True)

    result = {
        "meta": {
            "total": len(all_items),
            "scraped_at": datetime.now().isoformat(),
            "sources": len(SCRIPTS),
            "errors": len(errors),
        },
        "items": all_items,
    }

    out_file = out_dir / "html_reviews.json"
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ {len(all_items)} 条 ({len(errors)} errors, {elapsed}s) → {out_file}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
