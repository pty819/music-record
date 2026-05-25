#!/usr/bin/env python3
"""
fast-rss-scrape.py — 遍历所有 RSS 站，抓取最近 N 天文章，
输出结构化 JSON：[{site_id, site_name, title, url, pub_date, body}]
正文不截断。

用法:
  python3 fast-rss-scrape.py
  python3 fast-rss-scrape.py -o /tmp/out.json
  python3 fast-rss-scrape.py --days 3
  python3 fast-rss-scrape.py --date 2026-05-25
"""

import argparse
import feedparser
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SITES_JSON = Path.home() / ".minimax" / "music-sites" / "sites.json"
DEFAULT_DAYS = 2


def load_sites():
    with open(SITES_JSON) as f:
        data = json.load(f)
    return [
        s for s in data["sites"]
        if s.get("has_rss") and s.get("rss_url") and s.get("crawl_strategy") != "skip"
    ]


def parse_rss_date(entry):
    from time import mktime
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed)).date()
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed)).date()
    return None


def get_body(entry):
    """获取完整正文：优先 content:encoded，其次 summary/description。
    只去 HTML 标签，不做截断。"""
    body = ""
    if hasattr(entry, "content") and entry.content:
        body = entry.content[0].value if entry.content[0].value else ""
    if not body and hasattr(entry, "summary"):
        body = entry.summary
    if not body and hasattr(entry, "description"):
        body = entry.description
    # 去掉 HTML 标签，保留纯文本
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    # 解码常见 HTML entities
    body = body.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    body = body.replace("&quot;", '"').replace("&#39;", "'").replace("&#8230;", "…")
    return body


def scrape_site(site, cutoff_date):
    site_id = site["id"]
    name = site["name"]
    rss_url = site["rss_url"]

    print(f"  [{site_id}] {rss_url}", file=sys.stderr)

    feed = feedparser.parse(rss_url)
    entries = feed.entries if hasattr(feed, "entries") else []
    if not entries:
        print(f"  [{site_id}] 0 条", file=sys.stderr)
        return []

    items = []
    for entry in entries:
        pub_date = parse_rss_date(entry)
        if pub_date is None or pub_date < cutoff_date:
            continue

        items.append({
            "site_id": site_id,
            "site_name": name,
            "title": entry.get("title", "").strip(),
            "url": entry.get("link", ""),
            "pub_date": pub_date.isoformat(),
            "body": get_body(entry),
        })

    print(f"  [{site_id}] {len(items)} 条 (≥ {cutoff_date})", file=sys.stderr)
    return items


def main():
    parser = argparse.ArgumentParser(description="快速 RSS 抓取 — 纯结构化输出")
    parser.add_argument("-o", "--output", help="输出 JSON 文件路径（缺省输出到 stdout）")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help=f"抓取最近 N 天（缺省 {DEFAULT_DAYS}）")
    parser.add_argument("--date", help="指定基准日期 YYYY-MM-DD（缺省今天）")
    args = parser.parse_args()

    ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date \
               else datetime.now(timezone.utc).date()
    cutoff_date = ref_date - timedelta(days=args.days)

    sites = load_sites()
    print(f"RSS 站数: {len(sites)}", file=sys.stderr)
    print(f"基准日期: {ref_date}  过滤: ≥ {cutoff_date}", file=sys.stderr)
    print(file=sys.stderr)

    all_items = []
    for site in sites:
        try:
            all_items.extend(scrape_site(site, cutoff_date))
        except Exception as e:
            print(f"  [{site['id']}] 💥 {e}", file=sys.stderr)

    all_items.sort(key=lambda r: r["pub_date"], reverse=True)

    result = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "ref_date": ref_date.isoformat(),
            "days_back": args.days,
            "total_entries": len(all_items),
        },
        "items": all_items,
    }

    output = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"\n✅ {len(all_items)} 条 → {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()