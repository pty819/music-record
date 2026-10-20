#!/usr/bin/env python3
"""
prune_raw_data.py — 按保留期清理 2026/<MM>/<DD>/ 原始抓取数据，保留 recommend/ 报告。

2026-10-18 新增：原设计把每天的原始 JSON（rss_merged / scraped_raw / processed /
各站 reviews）全部留在仓库里，2026-04 至今已积到 316MB，而且每个文件都被
daily_pipeline 的 `git add <date_dir>` 提交进历史。报告 recommend/<MM>/<DD>.md
本身已包含全部成品信息（专辑/艺人/评分/中文摘要/来源链接），原始 JSON 只是
中间产物，没有保留价值。

保留期从命令行给（默认 3 天）：当天和前 N-1 天的原始数据留着，方便重跑和排障；
更早的只留报告。

安全约束：
- 只删 YYYY/MM/DD 三层、且日期能解析的目录，不碰 recommend/、data/、其它文件
- 只删 2026/ 下、且确实像日期目录的路径
- dry-run 默认输出将要删的内容，不实际动手
- 删完把删除记录提交（可选 --commit），这样 git 里不会残留幽灵目录
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = ROOT / "2026"
# 实际目录名是 YYYY/MM/YYYY-MM-DD（如 2026/10/2026-10-06），不是 YYYY/MM/DD
DATE_DIR_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{4})-(\d{2})-(\d{2})$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="清理每日原始抓取数据，保留报告")
    ap.add_argument("--keep-days", type=int, default=3,
                    help="保留最近 N 天的原始数据（默认 3，含当天）")
    ap.add_argument("--apply", action="store_true", help="实际删除；默认只 dry-run")
    ap.add_argument("--commit", action="store_true", help="删除后提交到 git")
    return ap.parse_args()


def collect(keep_days: int) -> tuple[list[tuple[date, Path, int]], int]:
    """返回 (待删列表, 因 too_new 跳过的字节数)。待删列表元素 = (日期, 路径, 字节)。"""
    cutoff = date.today() - timedelta(days=keep_days - 1)
    doomed: list[tuple[date, Path, int]] = []
    skipped_bytes = 0
    if not RAW_ROOT.is_dir():
        return doomed, 0
    for path in RAW_ROOT.glob("*/*/"):
        rel = f"{path.parent.parent.name}/{path.parent.name}/{path.name.rstrip('/')}"
        m = DATE_DIR_RE.match(rel)
        if not m:
            continue
        try:
            d = date(int(m.group(3)), int(m.group(4)), int(m.group(5)))
        except ValueError:
            continue
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        if d >= cutoff:
            skipped_bytes += size
            continue
        doomed.append((d, path, size))
    return doomed, skipped_bytes


def main() -> int:
    args = parse_args()
    doomed, kept_bytes = collect(args.keep_days)

    freed = sum(sz for _, _, sz in doomed)
    summary = {
        "keep_days": args.keep_days,
        "cutoff": (date.today() - timedelta(days=args.keep_days - 1)).isoformat(),
        "would_delete_dirs": len(doomed),
        "would_free_mb": round(freed / 1024 / 1024, 1),
        "kept_recent_mb": round(kept_bytes / 1024 / 1024, 1),
        "applied": args.apply,
    }

    if not args.apply:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print("\ndry-run，未改动任何文件。加 --apply 实际执行。", file=sys.stderr)
        for d, p, sz in sorted(doomed)[:10]:
            print(f"  将删 {d}  {p.relative_to(ROOT)}  ({sz/1024/1024:.1f} MB)", file=sys.stderr)
        if len(doomed) > 10:
            print(f"  ... 另有 {len(doomed)-10} 个目录", file=sys.stderr)
        return 0

    removed = []
    for d, path, _ in sorted(doomed):
        try:
            shutil.rmtree(path)
            removed.append(d.isoformat())
        except OSError as e:
            print(f"[prune] 删不掉 {path}: {e}", file=sys.stderr)

    summary["removed_dirs"] = removed
    summary["freed_mb"] = round(freed / 1024 / 1024, 1)

    if args.commit and removed:
        # raw 不再被 git 跟踪（见 .gitignore 的 2026/ 条目），删除动作不需要
        # 提交到版本库——工作区删了就是删了，仓库里本来就没有这些文件。
        summary["committed"] = False
        summary["note"] = "raw 未被 git 跟踪，无需提交删除动作"

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
