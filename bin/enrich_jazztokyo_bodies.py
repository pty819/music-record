#!/usr/bin/env python3
"""
enrich_jazztokyo_bodies.py — fill jazztokyo_reviews.json `body` from the article page.

Why: https://jazztokyo.org/feed/ (WordPress RSS) exposes only the Japanese
lead paragraph in <description>/<content:encoded>; the full article text lives
in the page's <div class="cm-post-content"> block. The task spec requires the
untruncated full body, so after the RSS pass we fetch each item's article URL
over plain HTTP and replace the body when the page text is longer.

Usage:
    python3 bin/enrich_jazztokyo_bodies.py \
        --json 2026/11/2026-11-20/jazztokyo_reviews.json
"""
import argparse
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TIMEOUT = 30

# Candidate content containers, most specific first. cm-entry-summary holds the
# article paragraphs only (cm-post-content also carries the category/date/author
# header and the share-button + tag footer).
CONTENT_SELECTORS = [
    "div.cm-entry-summary",
    "div.cm-post-content",
    "div.entry-content",
    "article",
    "div.post-content",
]


# Article text ends where the theme's share/tag footer starts.
SHARE_MARKERS = ["共有:", "Tweet", "Reddit で共有", "友達にメールでリンクを送信", "いいね:"]


def strip_share_footer(text):
    """Drop the trailing share-button / tag block if it sits in the last half."""
    cut = None
    for marker in SHARE_MARKERS:
        pos = text.find(marker)
        if pos != -1 and pos > len(text) * 0.5:
            cut = pos if cut is None else min(cut, pos)
    if cut is None:
        return text
    return text[:cut].rstrip()


def fetch_text(url):
    """Return plain-text article body, or '' when the page is unusable."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code != 200:
            sys.stderr.write(f"  HTTP {r.status_code} for {url}\n")
            return ""
        r.encoding = r.apparent_encoding or r.encoding
        soup = BeautifulSoup(r.text, "lxml")
        node = None
        for sel in CONTENT_SELECTORS:
            node = soup.select_one(sel)
            if node:
                break
        if node is None:
            sys.stderr.write(f"  no content container for {url}\n")
            return ""
        for br in node.find_all("br"):
            br.replace_with("\n")
        for p in node.find_all(["p", "li", "h1", "h2", "h3", "h4"]):
            p.append("\n")
        text = node.get_text()
        text = re.sub(r"[ \t\u3000]+", " ", text)
        text = re.sub(r"\n\s*\n\s*", "\n\n", text)
        return strip_share_footer(text.strip())
    except Exception as e:
        sys.stderr.write(f"  fetch failed for {url}: {e}\n")
        return ""


def main():
    ap = argparse.ArgumentParser(description="Enrich JazzTokyo bodies from article pages")
    ap.add_argument("--json", required=True, help="path to jazztokyo_reviews.json")
    ap.add_argument("--min-len", type=int, default=200,
                    help="only enrich bodies shorter than this (default 200)")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    enriched = 0
    for item in items:
        url = item.get("url", "")
        cur = item.get("body") or ""
        if len(cur) >= args.min_len:
            sys.stderr.write(f"SKIP (body {len(cur)} >= {args.min_len}): {url}\n")
            continue
        text = fetch_text(url)
        if len(text) > len(cur):
            item["body"] = text
            item["excerpt"] = text[:500]
            enriched += 1
            sys.stderr.write(f"ENRICHED {len(cur)} -> {len(text)}: {url}\n")
        else:
            sys.stderr.write(f"NO-IMPROVEMENT (rss={len(cur)} page={len(text)}): {url}\n")

    data.setdefault("meta", {})["body_source"] = "plain_http_article_page" if enriched else "rss_only"
    data["meta"]["bodies_enriched"] = enriched

    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"Wrote {args.json} ({len(items)} items, {enriched} enriched)\n")


if __name__ == "__main__":
    main()
