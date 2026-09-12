#!/usr/bin/env python3
"""music-daily-recs 出货管道。无 LLM，无 Kanban AND 门。

04:00 cron (no_agent) 跑整条：
  RSS → HTML → merge → 评分 → 报告 → git push → 末尾 spawn 5 个 Camoufox worker

07:00 watchdog 复用本脚本：缺报告就出货；尾巴 JSON 后到了就再 merge 补 push。

出货不依赖任何 worker complete。Boomkat / JazzTokyo 失败不得挡住当天报告。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path("/home/liyifan/music-record")
BIN = ROOT / "bin"
LOCK_PATH = Path("/tmp/music-daily-recs.lock")
MIN_SCORE = 3


def _log(msg: str) -> None:
    print(msg, flush=True)


def run(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int | None = None,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    _log(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        timeout=timeout,
        check=check,
        text=True,
        capture_output=capture,
    )


def date_dir_for(d: date) -> Path:
    return ROOT / "2026" / d.strftime("%m") / d.isoformat()


def report_path_for(d: date) -> Path:
    return ROOT / "recommend" / d.strftime("%Y") / d.strftime("%m") / f"{d.isoformat()}.md"


def acquire_lock() -> int:
    fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        _log("另一条管道正在跑（flock），本进程退出 0，避免双开评分。")
        sys.exit(0)
    os.write(fd, f"{os.getpid()} {datetime.now().isoformat()}\n".encode())
    return fd


def git_pull() -> None:
    r = run(["git", "pull", "--ff-only", "origin", "main"], check=False, timeout=120)
    if r.returncode != 0:
        _log("git pull 失败，继续用磁盘上的代码出货。")


def scrape_rss(date_dir: Path, days: str) -> None:
    date_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            "python3",
            str(BIN / "fast-rss-scrape.py"),
            "--days",
            days,
            "-o",
            str(date_dir / "rss_merged.json"),
        ],
        timeout=3600,
    )


def scrape_html(date_dir: Path, days: str) -> None:
    date_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            "python3",
            str(BIN / "scrape_html_parallel.py"),
            "--out-dir",
            str(date_dir),
            "--days",
            days,
            "--timeout",
            "180",
        ],
        timeout=3600,
    )
    stray = ROOT / "html_reviews.json"
    dest = date_dir / "html_reviews.json"
    if stray.exists() and not dest.exists():
        stray.replace(dest)
        _log(f"已把 CWD html_reviews.json 挪到 {dest}")


def merge(date_dir: Path) -> int:
    r = run(
        [
            "python3",
            str(BIN / "merge_scraped.py"),
            "--date-dir",
            str(date_dir),
            "-o",
            "scraped_raw.json",
        ],
        check=False,
        timeout=120,
        capture=True,
    )
    if r.stderr:
        _log(r.stderr.rstrip())
    raw_path = date_dir / "scraped_raw.json"
    if r.returncode != 0 or not raw_path.exists():
        payload = {
            "meta": {
                "total": 0,
                "merged_from": {},
                "scraped_at": datetime.now().isoformat(),
                "empty": True,
            },
            "items": [],
        }
        raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        _log("merge 0 条，写了空 scraped_raw.json，继续出货。")
        return 0
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    return len(data.get("items") or [])


def write_empty_processed(date_dir: Path, reason: str) -> None:
    payload = {
        "meta": {
            "total": 0,
            "empty": True,
            "reason": reason,
            "processed_at": datetime.now().isoformat(),
        },
        "items": [],
    }
    (date_dir / "processed.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def write_report(d: date, date_dir: Path, items: list) -> Path:
    out = report_path_for(d)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not items:
        md = (
            f"# 🎵 每日音乐推荐 — {d.isoformat()}\n\n"
            "共整理 0 条乐评，筛选 0 条推荐。\n\n"
            f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
            "*数据来源：0 条乐评 → 推荐 0 条*\n"
        )
        out.write_text(md, encoding="utf-8")
        _log(f"空报告 → {out}")
        return out
    r = run(
        [
            "python3",
            str(BIN / "generate_report.py"),
            "--date-dir",
            str(date_dir),
            "-i",
            "processed.json",
            "--date",
            d.isoformat(),
            "--min-score",
            str(MIN_SCORE),
        ],
        timeout=60,
    )
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"generate_report.py 失败，报告不在 {out}")
    return out


def score(date_dir: Path) -> int:
    raw_path = date_dir / "scraped_raw.json"
    if not raw_path.exists():
        write_empty_processed(date_dir, "no scraped_raw.json")
        return 0
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    n = len(data.get("items") or [])
    if n == 0:
        write_empty_processed(date_dir, "scraped_raw empty")
        return 0
    r = run(
        [
            "python3",
            str(BIN / "process_reviews.py"),
            "--date-dir",
            str(date_dir),
            "-i",
            "scraped_raw.json",
            "-o",
            "processed.json",
            "--max-workers",
            "3",
        ],
        check=False,
        timeout=3300,
    )
    proc_path = date_dir / "processed.json"
    if r.returncode != 0 or not proc_path.exists():
        raise SystemExit(f"process_reviews.py 失败 rc={r.returncode}")
    processed = json.loads(proc_path.read_text(encoding="utf-8"))
    items = processed.get("items") or []
    low = [i for i in items if i.get("total_score", 0) <= 2]
    if low:
        raise SystemExit(f"processed.json 仍有 {len(low)} 条 <=2 分，拒绝 push")
    return len(items)


def git_push_daily(d: date, date_dir: Path) -> bool:
    report = report_path_for(d)
    paths = [
        str(date_dir.relative_to(ROOT)),
        str(report.relative_to(ROOT)),
        "data/fluid_radio_archive.json",
    ]
    run(["git", "add", "--"] + paths, check=False)
    # 日更提交不带日志
    for extra in list(date_dir.glob("*_log.txt")) + list(date_dir.glob("*.log")):
        run(["git", "reset", "HEAD", "--", str(extra.relative_to(ROOT))], check=False)
    run(["git", "reset", "HEAD", "--", "logs/"], check=False)
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(ROOT),
        check=False,
    )
    if status.returncode == 0:
        _log("没有要提交的日更文件（可能已经 push 过）。")
        return False
    msg = f"music-recs: {d.isoformat()} daily recommendations"
    r = run(["git", "commit", "-m", msg], check=False)
    if r.returncode != 0:
        _log("git commit 无变更或失败。")
        return False
    r = run(["git", "push", "origin", "main"], check=False, timeout=180)
    if r.returncode != 0:
        raise SystemExit("git push 失败，报告已在本地。看上面的实际错误，不要归因 GFW。")
    _log(f"已 push origin/main：{msg}")
    return True


def spawn_swarm() -> None:
    r = run(["python3", str(BIN / "kanban-swarm.py"), "--confirm"], check=False, timeout=120)
    if r.returncode != 0:
        _log(f"kanban-swarm.py 失败 rc={r.returncode}。出货已完成，探索 worker 未创建。")


def report_on_origin(d: date) -> bool:
    rel = f"recommend/{d.strftime('%Y')}/{d.strftime('%m')}/{d.isoformat()}.md"
    r = subprocess.run(
        ["git", "cat-file", "-e", f"origin/main:{rel}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def newest_reviews_mtime(date_dir: Path) -> float:
    mtimes = []
    for p in date_dir.glob("*_reviews.json"):
        try:
            mtimes.append(p.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else 0.0


def processed_mtime(date_dir: Path) -> float:
    p = date_dir / "processed.json"
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="music-daily-recs 出货管道（无 LLM）")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--days", default="1.5")
    p.add_argument("--skip-scrape", action="store_true", help="跳过 RSS/HTML，用已有 JSON")
    p.add_argument("--skip-swarm", action="store_true", help="不创建 Camoufox worker")
    p.add_argument("--skip-score", action="store_true", help="跳过评分（已有 processed.json）")
    p.add_argument("--skip-push", action="store_true")
    p.add_argument(
        "--if-needed",
        action="store_true",
        help="watchdog：报告已在 origin/main 且无更新尾巴则静默退出",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    lock_fd = acquire_lock()
    try:
        os.chdir(ROOT)
        d = date.fromisoformat(args.date) if args.date else date.today()
        date_dir = date_dir_for(d)
        date_dir.mkdir(parents=True, exist_ok=True)

        if args.if_needed:
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(ROOT),
                check=False,
                timeout=60,
                capture_output=True,
            )
            on_origin = report_on_origin(d)
            stale_tail = newest_reviews_mtime(date_dir) > processed_mtime(date_dir) + 1
            if on_origin and not stale_tail:
                return 0  # no_agent 空 stdout = 不投递
            _log(
                f"watchdog 补货 {d.isoformat()}: "
                f"on_origin={on_origin} stale_tail={stale_tail}"
            )
            args.skip_scrape = (date_dir / "rss_merged.json").exists()
            args.skip_swarm = True

        git_pull()

        if not args.skip_scrape:
            scrape_rss(date_dir, args.days)
            scrape_html(date_dir, args.days)

        n_raw = merge(date_dir)
        _log(f"merge {n_raw} 条")

        if args.skip_score and (date_dir / "processed.json").exists():
            processed = json.loads((date_dir / "processed.json").read_text(encoding="utf-8"))
            items = processed.get("items") or []
            n_kept = len(items)
        else:
            n_kept = score(date_dir)
            processed = json.loads((date_dir / "processed.json").read_text(encoding="utf-8"))
            items = processed.get("items") or []

        write_report(d, date_dir, items)
        _log(f"保留 {n_kept} 条 >=3 分 → {report_path_for(d)}")

        pushed = False
        if not args.skip_push:
            pushed = git_push_daily(d, date_dir)

        if not args.skip_swarm:
            spawn_swarm()

        _log(
            f"DONE {d.isoformat()} raw={n_raw} kept={n_kept} "
            f"pushed={pushed} report={report_path_for(d)}"
        )
        return 0
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
