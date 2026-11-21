#!/usr/bin/env python3
"""
scrape_boomkat_rss.py — Boomkat new-releases scraper (RSS route).

Boomkat (https://boomkat.com/) — experimental / electronic / noise / ambient
release reviews. Camofox and plain browser requests are Cloudflare-blocked
from this host ("Just a moment..." interstitial, never resolves), but the
public RSS feed https://boomkat.com/new-releases.rss is reachable with a
plain urllib request carrying a browser User-Agent.

The feed summary carries the FULL review text in a <div class="trix-content">
block, plus three <p> fields (genre / label / format) and a link to the
product page. Entries whose summary has no trix-content block are releases
without editorial copy (verified against their product pages) and are
skipped, matching the 2026-11-18 reference output.

Usage:
  python3 scrape_boomkat_rss.py [--days 1.5] [--out boomkat_reviews.json]
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
FEED = "https://boomkat.com/new-releases.rss"

SITE_ID = "boomkat"
SOURCE = "Boomkat"
TAGS = "experimental,electronic,noise,ambient,modern composition"

NON_MUSIC_RE = re.compile(r"\((BLU-RAY|UHD|VOD|DVD)\)", re.IGNORECASE)
NON_MUSIC_FMT_RE = re.compile(r"\b(Blu-?Ray|DVD|VHD|VOD)\b", re.IGNORECASE)
TRIX_RE = re.compile(r'<div class="trix-content">(.*?)</div>', re.S)
P_RE = re.compile(r"<p>(.*?)</p>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,text/xml,*/*"})
    return urllib.request.urlopen(req, timeout=45).read()


def strip_html(raw):
    txt = re.sub(r"<br\s*/?>", "\n", raw)
    txt = re.sub(r"</p>", "\n\n", txt)
    txt = TAG_RE.sub("", txt)
    txt = txt.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    txt = txt.replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n\s*\n+", "\n\n", txt)
    return txt.strip()


def entry_date(entry):
    stamp = entry.get("published") or entry.get("updated") or ""
    try:
        dt = parsedate_to_datetime(stamp)
    except Exception:
        return None
    return dt.date()


def split_title(title):
    if " - " in title:
        artist, album = title.split(" - ", 1)
        return artist.strip(), album.strip()
    return title.strip(), ""


def build_item(entry):
    summary = entry.get("summary") or ""
    trix = TRIX_RE.findall(summary)
    if not trix:
        return None
    body = strip_html(trix[0])
    if not body:
        return None
    title = (entry.get("title") or "").strip()
    if NON_MUSIC_RE.search(title):
        return None
    paras = [strip_html(p) for p in P_RE.findall(summary)]
    genre = paras[0] if len(paras) > 0 else ""
    label = paras[1] if len(paras) > 1 else ""
    fmt = paras[2] if len(paras) > 2 else ""
    if NON_MUSIC_FMT_RE.search(fmt) or NON_MUSIC_FMT_RE.search(title):
        return None
    artist, album = split_title(title)
    return {
        "album": album,
        "artist": artist,
        "score": None,
        "url": (entry.get("link") or "").strip(),
        "source": SOURCE,
        "pub_date": entry_date(entry).isoformat(),
        "tags": TAGS,
        "excerpt": body[:500],
        "body": body,
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": "review",
        "label": label,
        "genre": genre,
        "format": fmt,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=1.5)
    ap.add_argument("--out", default="")
    ap.add_argument("--max-pages", type=int, default=12)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=args.days)).date()

    items = []
    seen = set()
    scanned = 0
    pages = 0
    empty_streak = 0

    for page in range(1, args.max_pages + 1):
        url = FEED if page == 1 else FEED + "?page=%d" % page
        try:
            raw = fetch(url)
        except Exception as exc:
            print("page %d fetch failed: %s" % (page, exc), file=sys.stderr)
            break
        parsed = feedparser.parse(raw)
        entries = parsed.entries
        if not entries:
            break
        pages += 1
        in_window = 0
        for entry in entries:
            scanned += 1
            d = entry_date(entry)
            if d is None or d < cutoff:
                continue
            in_window += 1
            item = build_item(entry)
            if item is None:
                continue
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            items.append(item)
        # The feed is ordered newest-first but with date jitter (a page can mix
        # 19 Nov and 17 Nov entries), so only stop after two consecutive pages
        # with no in-window entry at all.
        if in_window == 0:
            empty_streak += 1
            if empty_streak >= 2:
                break
        else:
            empty_streak = 0

    payload = {
        "meta": {
            "total": len(items),
            "scraped_at": now.isoformat(),
            "cutoff_date": cutoff.isoformat(),
            "site": SITE_ID,
            "source": "boomkat.com/new-releases.rss (summary trix-content = full review)",
            "method": "urllib + feedparser (Camofox and plain browser requests are Cloudflare-blocked)",
            "rss_items_scanned": scanned,
            "pages_scanned": pages,
            "window": "%gh" % round(args.days * 24),
        },
        "items": items,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("wrote %s (%d items, %d entries scanned)" % (args.out, len(items), scanned))
    else:
        print(text)


if __name__ == "__main__":
    main()
