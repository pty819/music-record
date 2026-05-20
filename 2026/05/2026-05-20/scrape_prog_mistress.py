#!/usr/bin/env python3
"""Scrape Prog Mistress (progmistress.com)"""

import subprocess
import re
import json
import feedparser
from datetime import datetime, timedelta, timezone

FEED_URL = "https://progmistress.com/feed/"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-20/prog_mistress_reviews.json"
CUTOFF_DAYS = 3

# Get feed via curl
result = subprocess.run(
    ["curl", "-s", "--max-time", "20", FEED_URL],
    capture_output=True, text=True
)
feed_text = result.stdout

feed = feedparser.parse(feed_text)

cutoff = datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)
print(f"Cutoff: {cutoff}")
print(f"Total entries: {len(feed.entries)}")

recent_items = []
for entry in feed.entries:
    try:
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
        else:
            continue
        print(f"  {pub_dt} - {entry.title[:60]}")
        if pub_dt >= cutoff:
            recent_items.append(entry)
    except Exception as e:
        print(f"  Error parsing: {e}")

print(f"\nRecent items (within {CUTOFF_DAYS} days): {len(recent_items)}")

# Check the latest item dates
if feed.entries:
    for e in feed.entries[:5]:
        pub = e.get("published_parsed")
        if pub:
            dt = datetime(*pub[:6], tzinfo=timezone.utc)
            print(f"  {dt} - {e.title[:60]}")

# Extract full review info
reviews = []
for item in recent_items:
    # Get full content from summary or description
    summary = item.get("summary", "") or item.get("description", "") or ""
    # Strip HTML
    summary_text = re.sub(r'<[^>]+>', '', summary).strip()
    excerpt = summary_text[:500] if summary_text else ""

    # Try to parse artist/album from title
    title = item.title
    artist = ""
    album = title

    # Look for "Artist - Album" pattern
    if " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        album = parts[1].strip()

    # Check for non-music (BLU-RAY, DVD, etc.)
    non_music = any(kw in (artist + album).upper() for kw in ["BLU-RAY", "BLU RAY", "UHD", "VOD", "DVD"])
    if non_music:
        print(f"  SKIP (non-music): {artist} - {album}")
        continue

    # Get score if present
    score = None
    score_match = re.search(r'(\d+)/10', summary_text)
    if score_match:
        score = int(score_match.group(1))

    # Get categories/tags
    tags = [cat.label if hasattr(cat, 'label') else str(cat) for cat in item.get('tags', [])]

    # Determine type
    item_type = "review"
    if any(kw in summary_text.lower() for kw in ["interview", "feature", "documentary", "podcast"]):
        item_type = "feature"

    url = item.get("link", "")
    pub_date = ""
    if item.get("published_parsed"):
        pub_date = datetime(*item.published_parsed[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d")

    review = {
        "album": album,
        "artist": artist,
        "score": score,
        "url": url,
        "source": "Prog Mistress",
        "pub_date": pub_date,
        "tags": tags,
        "excerpt": excerpt,
        "site_id": "prog_mistress",
        "crawl_status": "success",
        "type": item_type
    }
    reviews.append(review)
    print(f"  ADDED: {artist} - {album} ({pub_date}) score={score}")

print(f"\nTotal reviews to write: {len(reviews)}")

with open(OUTPUT_FILE, "w") as f:
    json.dump(reviews, f, indent=2, ensure_ascii=False)

print(f"Written to {OUTPUT_FILE}")
