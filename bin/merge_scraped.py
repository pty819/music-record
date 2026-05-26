#!/usr/bin/env python3
"""
merge_scraped.py — 合并 RSS + HTML/Camoufox 原始抓取数据到统一文件。

读取数据目录下所有：
  - rss_merged.json（RSS 批量抓取结果）
  - *_reviews.json（各站独立抓取结果）
去重（按 url）、排序（按 pub_date 降序）、写入 output 文件。

统一输出格式：{meta: {total, merged_from, scraped_at}, items: [...]}

用法:
  python3 merge_scraped.py --date-dir 2026/05/2026-05-26
  python3 merge_scraped.py --date-dir 2026/05/2026-05-26 -o reviews_all.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def merge_dir(date_dir, dedup=True):
    """
    Merge all scraped JSON files in date_dir into one list of items.
    Returns (items, source_counts) where source_counts is a dict of filename->count.
    """
    base = Path(date_dir)
    if not base.is_dir():
        print(f"ERROR: directory not found: {date_dir}", file=sys.stderr)
        sys.exit(1)

    all_items = []
    source_counts = {}

    # Find all relevant JSON files
    patterns = ["rss_merged.json"]
    patterns.extend(str(p) for p in sorted(base.glob("*_reviews.json")))

    for fpath in patterns:
        if isinstance(fpath, str):
            fpath = base / fpath
        if not fpath.exists() or fpath.stat().st_size < 5:
            continue
        if fpath.name in ("aggregated.json", "filtered.json"):
            continue  # skip aggregator outputs

        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ⚠ {fpath.name}: json error ({e}), skip", file=sys.stderr)
            continue

        items = []
        if isinstance(raw, dict) and "items" in raw:
            items = raw["items"]
        elif isinstance(raw, list):
            items = raw
        else:
            print(f"  ⚠ {fpath.name}: unknown format ({type(raw).__name__}), skip", file=sys.stderr)
            continue

        if not items:
            continue

        # Ensure each item has a site_id for tracing
        for item in items:
            if "site_id" not in item or not item.get("site_id"):
                # Infer from filename
                stem = fpath.stem
                if stem == "rss_merged":
                    item["site_id"] = "rss_merged"
                else:
                    item["site_id"] = stem.replace("_reviews", "")

        all_items.extend(items)
        source_counts[fpath.name] = len(items)
        print(f"  {fpath.name:<40s} {len(items):>4d} items", file=sys.stderr)

    if dedup:
        # Dedup by URL (keep first occurrence = prefer RSS source)
        seen = set()
        deduped = []
        dups = 0
        for item in all_items:
            url = item.get("url", "")
            if not url:
                deduped.append(item)
                continue
            if url in seen:
                dups += 1
                continue
            seen.add(url)
            deduped.append(item)
        if dups:
            print(f"  🔄 dedup removed {dups} duplicates (kept RSS version)", file=sys.stderr)
        all_items = deduped

    # Sort by pub_date descending (newest first)
    all_items.sort(key=lambda r: r.get("pub_date", ""), reverse=True)

    return all_items, source_counts


def main():
    parser = argparse.ArgumentParser(description="Merge RSS + HTML scraped data into unified file")
    parser.add_argument("--date-dir", required=True, help="数据目录（如 2026/05/2026-05-26）")
    parser.add_argument("-o", "--output", default="scraped_raw.json", help="输出文件名（默认 scraped_raw.json）")
    parser.add_argument("--no-dedup", action="store_false", dest="dedup", help="跳过 URL 去重")
    args = parser.parse_args()

    # Resolve date_dir
    if args.date_dir.startswith("/"):
        date_dir = args.date_dir
    else:
        base_dir = Path(__file__).resolve().parent.parent
        date_dir = str(base_dir / args.date_dir)

    print(f"📂 数据目录: {date_dir}", file=sys.stderr)
    items, sources = merge_dir(date_dir, dedup=args.dedup)

    if not items:
        print("❌ 没有找到任何数据", file=sys.stderr)
        sys.exit(1)

    # Build merged output
    result = {
        "meta": {
            "total": len(items),
            "merged_from": {k: v for k, v in sorted(sources.items())},
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        },
        "items": items,
    }

    output_path = Path(date_dir) / args.output
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\n✅ {len(items)} 条 → {output_path}", file=sys.stderr)
    print(f"   来源: {len(sources)} 个文件", file=sys.stderr)

    # Also print to stdout for pipe use
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()