#!/usr/bin/env python3
"""
Bandwagon Asia scraper - uses articles.atom RSS feed
"""
import json, re, sys
from datetime import datetime, timedelta, timezone
import feedparser

# --- config ---
OUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-24/bandwagon_asia_reviews.json"
RSS_URL = "https://www.bandwagon.asia/feeds/articles.atom"
CUTOFF_DAYS = 3
SITE_ID = "bandwagon_asia"
SITE_URL = "https://www.bandwagon.asia"
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=CUTOFF_DAYS)
print(f"Cutoff: {CUTOFF.date()} ({CUTOFF.isoformat()})", file=sys.stderr)

def parse_date(date_str):
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except:
        pass
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except:
            pass
    return None

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def classify_type(title):
    title_lower = title.lower()
    if any(k in title_lower for k in ['interview', 'feature', 'artist spotlight', 'preview', 'premiere', 'spotlight']):
        return "feature"
    if any(k in title_lower for k in ['tracklist', 'track list', 'track listing', 'tracklist']):
        return "tracklist"
    return "review"

# --- parse RSS ---
print(f"Fetching RSS: {RSS_URL}", file=sys.stderr)
import socket
old_timeout = socket.getdefaulttimeout()
socket.setdefaulttimeout(20)
feed = feedparser.parse(RSS_URL)
socket.setdefaulttimeout(old_timeout)

print(f"Feed entries: {len(feed.entries)}", file=sys.stderr)

items = []
for entry in feed.entries:
    # Parse date
    pub_date = None
    for date_field in ['published', 'updated', 'published_parsed']:
        val = getattr(entry, date_field, None)
        if val:
            if isinstance(val, (tuple, list)) and len(val) >= 6:
                try:
                    pub_date = datetime(*val[:6], tzinfo=timezone.utc)
                except:
                    pass
            else:
                pub_date = parse_date(str(val))
        if pub_date:
            break

    if not pub_date:
        print(f"  Could not parse date for: {entry.get('title', '')[:50]}", file=sys.stderr)
        continue

    print(f"  Entry date: {pub_date.date()} | {pub_date.isoformat()}", file=sys.stderr)
    print(f"  Cutoff:     {CUTOFF.date()} | {CUTOFF.isoformat()}", file=sys.stderr)

    if pub_date < CUTOFF:
        print(f"  SKIP (pre-cutoff): {entry.get('title', '')[:60]}", file=sys.stderr)
        continue

    title = entry.get('title', '') or ''
    link = entry.get('link', '') or entry.get('id', '') or ''

    # Filter non-music
    if any(x in title.upper() for x in ['(BLU-RAY)', '(UHD)', '(VOD)', '(DVD)', 'BLU-RAY']):
        print(f"  FILTERED (non-music): {title[:60]}", file=sys.stderr)
        continue

    # Get excerpt from content
    excerpt = ""
    content = entry.get('content', [])
    if content:
        for c in content:
            if c.get('value'):
                excerpt = strip_html(c.get('value', ''))
                break
    if not excerpt:
        summary = entry.get('summary', '')
        if summary:
            excerpt = strip_html(summary)

    # Classify type
    item_type = classify_type(title)

    items.append({
        "album": title,
        "artist": "",
        "score": None,
        "url": link,
        "source": SITE_URL,
        "pub_date": pub_date.isoformat() if pub_date else None,
        "tags": [],
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": item_type
    })
    print(f"  ADDED [{item_type}] {pub_date.date()} - {title[:70]}")

print(f"\nTotal items: {len(items)}", file=sys.stderr)

# Deduplicate by URL
seen = set()
deduped = []
for item in items:
    if item["url"] and item["url"] not in seen:
        seen.add(item["url"])
        deduped.append(item)
items = deduped

with open(OUT_FILE, 'w') as f:
    json.dump(items, f, indent=2, ensure_ascii=False)

print(f"Wrote {len(items)} items to {OUT_FILE}")
for item in items:
    print(f"  [{item['type']}] {item['pub_date'][:10]} {item['album'][:70]}")