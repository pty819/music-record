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
    # ── 需要 Chromium 渲染的站：2026-10-18 起从每日出货路径跳过 ──────────────
    # 本机（racknerd-d5dd0b）只有 1.6GB RAM，其中 Hermes 网关常驻约 545MB。
    # 实测单个 Chromium 站会拉起 ~74 个子进程、RSS 冲到 935MB，可用内存掉到
    # 137MB，内核 OOM killer 静默杀掉 chrome（dmesg 有记录），表现为
    # `empty stdout` + 0 条，且日志上看不出是内存问题。
    # 已试过：降低 V8 heap（已到 128MB 下限）、Chromium 站串行化 —— 均无效。
    # Pi 方案也不行：Pi 上 google-chrome 152 渲染同样挂死（jina-embed 的
    # llama-server 常驻 4GB，渲染时拿不到内存）。
    # 决定：每日只跑 RSS + 纯 HTTP 的 HTML 站，不再为 3 个站硬扛浏览器。
    # 下面三站需要 Chromium 渲染，已从本列表移除（脚本文件仍在 bin/，取消注释即恢复）：
    #   scrape_all_about_jazz / scrape_mixmag_asia / scrape_musique_machine
    # ── 纯 HTTP 站：无需浏览器，稳定 ───────────────────────────────────────
    ("scrape_bandwagon_asia",        "bandwagon_asia",           "stdout"),
    ("scrape_dark_entries",          "dark_entries_be",          "stdout"),
    ("scrape_downbeat",              "downbeat",                 "stdout"),  # HTTP 为主，Chromium 仅 fallback
    ("scrape_free_jazz_blog",        "free_jazz_blog",           "stdout"),
    ("scrape_hear65",                "hear65",                   "stdout"),
    ("scrape_jazz_trail",            "jazz_trail",               "stdout"),
    ("scrape_mikiki",                "mikiki",                    "stdout"),
    ("scrape_progressor",            "progressor",                "out_dir"),
    ("scrape_resident_advisor",      "resident_advisor",         "stdout"),
    ("scrape_roots_world",           "roots_world",              "stdout"),
    ("scrape_sea_of_tranquility",    "sea_of_tranquility",       "out_dir"),
    ("scrape_songlines",             "songlines",                "stdout"),
    ("scrape_squids_ear",            "squids_ear",               "stdout"),
    ("scrape_strangely_isolated_place", "strangely_isolated_place", "stdout"),
    # ── 2026-10-27 恢复：Camofox 站 ───────────────────────────────────────
    # 原来这 3 站被移除的理由是「单个 Chromium 站会拉起 ~74 个子进程、
    # RSS 冲到 935MB、OOM killer 静默杀 chrome」。那个理由在 Camofox 下
    # 不成立了：Camofox 是常驻服务（一个 Firefox 实例服务所有站），
    # 不是每个站拉起一个浏览器。
    # 但这 3 站要走真实网络栈 + CF 挑战，单站耗时远高于纯 HTTP 站：
    # mixmag 实测约 15s/篇 × 25 篇 ≈ 375s，所以要单独给 timeout。
    ("scrape_all_about_jazz",         "all_about_jazz",          "stdout", 180),
    ("scrape_mixmag_asia",            "mixmag_asia",             "stdout", 180),
    ("scrape_musique_machine",        "musique_machine",         "stdout", 120),
]
# NOTE: world_music_central 已迁移到 RSS 层（has_rss=True），不走 HTML 层。
# 若从 sites.json 移除 has_rss，需重新加回 SCRIPTS 并同步 kanban-swarm.py HTML_SCRIPT_IDS。


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


def run_scraper(script, site_id, mode, bin_dir, out_dir, days, timeout, site_timeout=None):
    """Run one scraper subprocess, return (site_id, items_list, error_str).

    `site_timeout` 覆盖全局 timeout —— 给 Camofox 站更长的预算
    （它们要等 CF 挑战 + 真实网络栈，纯 HTTP 站 180s 就够）。
    """
    script_path = os.path.join(bin_dir, f"{script}.py")
    eff_timeout = site_timeout or timeout
    cmd = ["timeout", str(eff_timeout), sys.executable, script_path, "--days", str(days)]

    if mode == "out_dir":
        cmd.extend(["--out-dir", str(out_dir)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=eff_timeout + 10)
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=eff_timeout + 10)
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

    # Run all scrapers concurrently via ThreadPoolExecutor.
    #
    # 2026-10-18: 原本这里把 4 个 Chromium 站单独串行跑（担心并发抢内存），
    # 但本机 1.6GB 扛不住 Chromium（见 SCRIPTS 上方注释），那三站已移出
    # 列表，现在剩下的全是纯 HTTP 站，原来的全并发即可。
    #
    # 2026-10-27: Camofox 站恢复进管道。Camofox 是常驻服务（一个 Firefox
    # 实例服务所有站），不再有「每站拉起一个浏览器」的内存问题。但
    # **Camofox 站之间必须串行** —— 实测并发 3 个 tab 全部建失败
    # （fork Firefox 进程时内存不足，available 掉到 387MB）。
    # 所以：纯 HTTP 站全并发，Camofox 站在 HTTP 站跑完后串行跑。
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_items = []
    errors = []
    t0 = time.monotonic()

    BROWSER_SITE_IDS = {"all_about_jazz", "mixmag_asia", "musique_machine"}
    http_scripts = [s for s in SCRIPTS if s[1] not in BROWSER_SITE_IDS]
    browser_scripts = [s for s in SCRIPTS if s[1] in BROWSER_SITE_IDS]

    def _collect(sid, items, err):
        if err:
            print(f"  {sid}: ❌ {err}", file=sys.stderr)
            errors.append((sid, err))
        else:
            print(f"  {sid}: ✅ {len(items)} items", file=sys.stderr)
            all_items.extend(items)

    def _run_one(entry):
        script, site_id, mode = entry[0], entry[1], entry[2]
        site_timeout = entry[3] if len(entry) > 3 else None
        return run_scraper(script, site_id, mode, args.bin_dir, str(out_dir),
                           args.days, args.timeout, site_timeout)

    # ── 第一批：纯 HTTP 站，全并发 ─────────────────────────────────
    if http_scripts:
        with ThreadPoolExecutor(max_workers=len(http_scripts)) as pool:
            futures = {pool.submit(_run_one, s): s[1] for s in http_scripts}
            for future in as_completed(futures):
                site_id = futures[future]
                try:
                    sid, items, err = future.result()
                    _collect(sid, items, err)
                except Exception as e:
                    print(f"  {site_id}: 💥 {e}", file=sys.stderr)
                    errors.append((site_id, str(e)))

    # ── 第二批：Camofox 站，串行（并发会 fork 失败）─────────────────
    for entry in browser_scripts:
        try:
            sid, items, err = _run_one(entry)
            _collect(sid, items, err)
        except Exception as e:
            print(f"  {entry[1]}: 💥 {e}", file=sys.stderr)
            errors.append((entry[1], str(e)))

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
