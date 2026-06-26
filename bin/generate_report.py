#!/usr/bin/env python3
"""
generate_report.py — 读取 processed.json，按评分排序，输出 recommend markdown。

零 API 调用，毫秒级。只做格式化，不做评分/总结。

用法:
  cd /home/liyifan/music-record
  python3 bin/generate_report.py --date-dir 2026/05/2026-05-27
  python3 bin/generate_report.py --date-dir 2026/05/2026-05-27 --date 2026-05-27 --min-score 5
"""
import argparse
import json
from datetime import date, datetime
from pathlib import Path


def generate_markdown(items, output_date, min_score=1, top_k=None):
    """Generate recommend markdown sorted by score descending.

    Args:
        items: list of review items (already sorted descending by total_score)
        output_date: YYYY-MM-DD string for the header
        min_score: minimum score to include (default 1, include all)
        top_k: if set, only show top K items

    Returns:
        markdown string
    """
    # Filter and truncate
    filtered = [i for i in items if i.get("total_score", 0) >= min_score]
    if top_k:
        filtered = filtered[:top_k]

    total_in = len(items)
    total_out = len(filtered)

    lines = []
    lines.append(f"# 🎵 每日音乐推荐 — {output_date}")
    lines.append("")
    lines.append(f"共整理 {total_in} 条乐评，筛选 {total_out} 条推荐。")
    lines.append(f"评分范围 {min_score}-10 分。")
    lines.append("")

    # Group by score tiers
    tiers = {
        "🌟 杰出 (9-10)": [i for i in filtered if i.get("total_score", 0) >= 9],
        "⭐ 优秀 (7-8)": [i for i in filtered if 7 <= i.get("total_score", 0) <= 8],
        "👍 不错 (5-6)": [i for i in filtered if 5 <= i.get("total_score", 0) <= 6],
        "🔹 一般 (3-4)": [i for i in filtered if 3 <= i.get("total_score", 0) <= 4],
        "📋 参考 (1-2)": [i for i in filtered if i.get("total_score", 0) <= 2],
    }

    for tier_name, tier_items in tiers.items():
        if not tier_items:
            continue
        lines.append(f"---")
        lines.append(f"## {tier_name}")
        lines.append("")
        for item in tier_items:
            score = item.get("total_score", 0)
            album = item.get("album", "未知专辑") or "未知专辑"
            artist = item.get("artist", "") or ""
            # Fallback for feature articles with no extractable title:
            # use the first line of the excerpt/article subject.
            if album == "未知专辑":
                excerpt = item.get("excerpt", "") or item.get("body", "") or ""
                first_line = excerpt.split("\n")[0].strip()[:80]
                if first_line:
                    album = first_line
            source = item.get("source", "未知来源") or ""
            url = item.get("url", "") or ""
            summary = item.get("_cn_summary", "") or ""
            genre = item.get("_genre", "") or ""
            tags = item.get("tags", "") or ""
            site_id = item.get("site_id", "") or ""

            artist_str = f" — {artist}" if artist else ""
            score_display = "⭐" * max(1, score // 2) + ("½" if score % 2 else "")

            lines.append(f"### {album}{artist_str}")
            if genre and genre != "unknown":
                lines.append(f"**风格**: {genre}")
            lines.append(f"**评分**: {score}/10  {score_display}")
            lines.append(f"**来源**: [{source}]({url})")

            if tags:
                lines.append(f"**标签**: {tags}")

            if summary and summary != "（评分失败）":
                lines.append(f"> {summary}")

            lines.append("")

    # Stats footer
    lines.append("---")
    lines.append(f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"*数据来源：{total_in} 条乐评 → 推荐 {total_out} 条*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="生成推荐 markdown，零 API 调用"
    )
    parser.add_argument("--date-dir", required=True, help="数据目录（如 2026/05/2026-05-27）")
    parser.add_argument("-i", "--input", default="processed.json", help="输入 JSON（默认 processed.json）")
    parser.add_argument("--date", default=str(date.today()), help="日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--min-score", type=int, default=1, help="最低评分（默认 1=全部）")
    parser.add_argument("--top-k", type=int, default=0, help="只显示前 K 条（默认全显示）")
    args = parser.parse_args()

    # Resolve paths
    if args.date_dir.startswith("/"):
        base_dir = Path(args.date_dir)
    else:
        base_dir = Path.cwd() / args.date_dir

    input_path = base_dir / args.input
    if not input_path.exists():
        print(f"❌ 输入文件不存在：{input_path}")
        return 1

    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = data.get("items", []) if isinstance(data, dict) else data

    if not items:
        print("❌ 输入文件没有条目")
        return 1

    # Items should already be sorted by score desc from process_reviews.py
    # But ensure it
    items.sort(key=lambda r: r.get("total_score", 0), reverse=True)

    md = generate_markdown(
        items,
        output_date=args.date,
        min_score=args.min_score,
        top_k=args.top_k if args.top_k > 0 else None,
    )

    output_path = Path.cwd() / "recommend" / f"{args.date}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")

    print(f"✅ {len(items)} 条 → 推荐 {sum(1 for i in items if i.get('total_score', 0) >= args.min_score)} 条")
    print(f"   输出: {output_path}")
    scores = [i.get("total_score", 0) for i in items]
    print(f"   最高分: {max(scores)}/10  最低分: {min(scores)}/10")


if __name__ == "__main__":
    main()
