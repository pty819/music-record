#!/usr/bin/env python3
import json

with open("/home/liyifan/music-record/2026/05/2026-05-16/icareifyoulisten_reviews.json") as f:
    data = json.load(f)

for item in data:
    print("Excerpt first 120:", repr(item["excerpt"][:120]))
    print()

# Rewrite cleaned
import re

ENTITIES = {
    '&#8216;': "'",
    '&#8217;': "'",
    '&#8220;': '"',
    '&#8221;': '"',
    '&#8230;': '…',
    '&#038;': '&',
    '&#160;': ' ',
    '&amp;': '&',
    '&nbsp;': ' ',
}

def clean_excerpt(raw_text):
    if not raw_text:
        return ""
    text = raw_text
    for entity, char in ENTITIES.items():
        text = text.replace(entity, char)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s*…?\s*Continued\s+The post.*?appeared first on.*?I CARE IF YOU LISTEN\.?\s*$',
                  '…', text, flags=re.IGNORECASE)
    text = text.strip()
    if len(text) > 500:
        text = text[:500].rsplit(' ', 1)[0] + '…'
    return text

# Get fresh data from feed
import feedparser
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

CUTOFF = datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc)
TODAY = datetime(2026, 5, 16, 23, 59, 59, tzinfo=timezone.utc)
SITE_ID = "icareifyoulisten"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-16/icareifyoulisten_reviews.json"

REVIEW_CATS = ['album', 'cd']
generic_cats = {'album', 'cd', 'concert', 'interview', 'playlist', 'premiere', 'essay', 'video', 'videos', 'interviews', 'concerts', 'albums', 'essays', 'listn up'}

feed = feedparser.parse("https://icareifyoulisten.com/feed")
results = []

for entry in feed.entries:
    pub_date_str = entry.get("published", "")
    if not pub_date_str:
        continue
    try:
        dt = parsedate_to_datetime(pub_date_str)
    except Exception:
        continue
    if dt < CUTOFF or dt > TODAY:
        continue

    categories = entry.get("tags", [])
    category_text = ' '.join([c.term.lower() for c in categories])
    article_type = "review" if any(cat in category_text for cat in REVIEW_CATS) else "feature"

    generic_cats_set = {'album', 'cd', 'concert', 'interview', 'playlist', 'premiere', 'essay', 'video', 'videos', 'interviews', 'concerts', 'albums', 'essays', 'listn up'}
    artist_cats = [c.term for c in categories if c.term.lower() not in generic_cats_set]
    artist = artist_cats[0] if artist_cats else ""
    album = entry.title
    url = entry.link

    raw_summary = entry.get("summary_detail", {}).get("value", "") or entry.get("summary", "") or ""
    excerpt = clean_excerpt(raw_summary)

    record = {
        "album": album,
        "artist": artist,
        "score": None,
        "url": url,
        "source": SITE_ID,
        "pub_date": dt.isoformat(),
        "tags": [t.term for t in categories[:8]],
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": article_type
    }
    results.append(record)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Written {len(results)} items")
for r in results:
    print(f"  [{r['type']}] {r['album'][:50]} | excerpt: {r['excerpt'][:80]}...")