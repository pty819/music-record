#!/usr/bin/env python3
"""
fetch_fluid_radio_archive.py — 一次性抓取 Fluid Radio category/reviews 全量存档。

Fluid Radio 的根 feed（/feed/）已被博彩 SEO 污染（Non GamStop Casino 系列），
但 category/reviews/feed/ 仍是干净的 2013-2022 ambient/electroacoustic 乐评。

本脚本分页抓取 category/reviews/feed/?paged=N，存成统一 JSON：
  data/fluid_radio_archive.json
  {meta: {total, scraped_at}, items: [{...rss 同构字段..., _last_picked_date: null}]}

用法:
  python3 bin/fetch_fluid_radio_archive.py                # 抓全量（79 页，~790 条）
  python3 bin/fetch_fluid_radio_archive.py --max-pages 5  # 测试抓前 5 页
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import feedparser

ARCHIVE_URL = "https://www.fluid-radio.co.uk/category/reviews/feed/"
OUT_FILE = Path(__file__).resolve().parent.parent / "data" / "fluid_radio_archive.json"
TAG_MAP = {"fluid_radio": "electronic ambient experimental"}

SITE_ID = "fluid_radio"
SOURCE = "Fluid Radio"


def get_body(entry):
    body = ""
    if hasattr(entry, "content") and entry.content:
        body = entry.content[0].value if entry.content[0].value else ""
    if not body and hasattr(entry, "summary"):
        body = entry.summary
    if not body and hasattr(entry, "description"):
        body = entry.description
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    body = body.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    body = body.replace("&quot;", '"').replace("&#39;", "'").replace("&#8230;", "…")
    return body


def parse_date(entry):
    from time import mktime
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed)).date().isoformat()
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed)).date().isoformat()
    return None


def parse_artist_album(title):
    for sep in [" — ", " – ", " - "]:
        parts = title.split(sep, 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    return "", title


def fetch_page(page):
    """Fetch one paged feed. Returns (page, items) or (page, None) if empty."""
    url = f"{ARCHIVE_URL}?paged={page}"
    feed = feedparser.parse(url)
    entries = feed.entries if hasattr(feed, "entries") else []
    if not entries:
        return page, None
    items = []
    seen = set()
    for e in entries:
        title = e.get("title", "").strip()
        link = e.get("link", "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        artist, album = parse_artist_album(title)
        body = get_body(e)
        pub_date = parse_date(e)
        items.append({
            "album": album,
            "artist": artist,
            "score": None,
            "url": link,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": TAG_MAP["fluid_radio"],
            "excerpt": body[:500],
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "archive",
            "type": "review",
            "_last_picked_date": None,  # 去重标记：哪天被随机抽中推送过
        })
    return page, items


def main():
    parser = argparse.ArgumentParser(description="抓 Fluid Radio category/reviews 全量存档")
    parser.add_argument("--max-pages", type=int, default=80,
                        help="最多抓多少页（默认 80，实际 ~79 页到底）")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    print(f"抓取 {ARCHIVE_URL} 最多 {args.max_pages} 页...", file=sys.stderr)

    all_items = []
    page_map = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_page, p): p for p in range(1, args.max_pages + 1)}
        for f in as_completed(futures):
            page, items = f.result()
            if items is not None:
                page_map[page] = items

    # 按页号排序（保持时间顺序）
    for p in sorted(page_map.keys()):
        all_items.extend(page_map[p])

    # 去重（按 url）
    seen = set()
    deduped = []
    for it in all_items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        deduped.append(it)

    result = {
        "meta": {
            "total": len(deduped),
            "pages_scanned": len(page_map),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "note": "Fluid Radio category/reviews 历史存档（2013-2022）。根 feed 已污染，本存档供随机抽取补充。",
        },
        "items": deduped,
    }
    OUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {len(deduped)} 条存档 → {OUT_FILE}（{len(page_map)} 页）", file=sys.stderr)


if __name__ == "__main__":
    main()
