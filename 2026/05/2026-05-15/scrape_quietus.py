#!/usr/bin/env python3
"""Scrape The Quietus album reviews - last 3 days only."""

import feedparser
import json
import re
import sys
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

CUTOFF_DAYS = 3
CUTOFF_DATE = datetime.now() - timedelta(days=CUTOFF_DAYS)
print(f"Cutoff date: {CUTOFF_DATE.date()}")

SITE_ID = "the_quietus"
TAGS = ["experimental", "electronic", "jazz", "world", "psych", "prog", "free-improv"]
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-15/the_quietus_reviews.json"

# -------------------------------------------------------------------
# 1. RSS
# -------------------------------------------------------------------
RSS_URLS = [
    "https://thequietus.com/columns/quietus-reviews/rss",
    "https://thequietus.com/columns/quietus-reviews/feed",
]

feed = None
for url in RSS_URLS:
    print(f"Trying RSS: {url}")
    feed = feedparser.parse(url)
    if feed.entries:
        print(f"  Got {len(feed.entries)} entries")
        break
    print(f"  No entries, status={getattr(feed, 'status', '?')}")

if not feed or not feed.entries:
    print("No RSS available, exiting with empty array")
    with open(OUTPUT_FILE, "w") as f:
        json.dump([], f)
    sys.exit(0)

# -------------------------------------------------------------------
# 2. Parse dates
# -------------------------------------------------------------------
def parse_date(date_str):
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except:
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None

# -------------------------------------------------------------------
# 3. Collect articles within cutoff
# -------------------------------------------------------------------
candidates = []
for entry in feed.entries:
    pub_date = parse_date(entry.get("published", ""))
    if not pub_date:
        continue
    pub_dt = pub_date.replace(tzinfo=None) if pub_date.tzinfo else pub_date
    if pub_dt < CUTOFF_DATE:
        print(f"  [SKIP old] {entry.get('title','')[:60]} — {pub_dt.date()}")
        continue
    candidates.append(entry)

print(f"\nCandidates within 3 days: {len(candidates)}")

# -------------------------------------------------------------------
# 4. Non-music filter
# -------------------------------------------------------------------
NON_MUSIC_KEYWORDS = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD', 'VIDEO GAME', 'FILM', 'DOCUMENTARY']

def is_non_music(album, artist):
    text = f"{album} {artist}".upper()
    return any(kw in text for kw in NON_MUSIC_KEYWORDS)

# -------------------------------------------------------------------
# 5. Parse artist/album/title
# -------------------------------------------------------------------
def parse_review_title(title):
    """
    Parse 'Artist – Album' format.
    Handles: 'Artist – Album', 'Artist – Album (Subtitle)', 'Artist: Album'
    Returns (artist, album).
    """
    # Try various separators
    for sep in [' – ', ' – ', ' — ', ' – ', ': ']:
        if sep in title:
            parts = title.split(sep, 1)
            artist = parts[0].strip()
            album = parts[1].strip()
            # Remove trailing review qualifiers
            album = re.sub(r'\s*[\(\[].*?[\)\]]\s*$', '', album).strip()
            return artist, album
    return "", title.strip()

def determine_type(title):
    """Determine if this is a review or feature/column."""
    t = title.lower()
    # Columns that are NOT traditional reviews
    non_review = ['straight hedge', 'spool\'s out', 'new weird britain', 'listening notes',
                  'hyperspecific', 'reissue of the week', 'live album of the week',
                  'album of the week', 'cassette reviews', 'electronic music for']
    for kw in non_review:
        if kw in t:
            return "feature"
    return "review"

# -------------------------------------------------------------------
# 6. Build items
# -------------------------------------------------------------------
items = []
for entry in candidates:
    title = entry.get("title", "")
    link = entry.get("link", "").split('?')[0]  # strip UTM params
    pub_date = parse_date(entry.get("published", ""))

    # Get excerpt from RSS summary (often full text for The Quietus)
    raw_summary = entry.get("summary", "") or entry.get("description", "") or ""
    # Strip HTML tags
    summary_text = re.sub(r'<[^>]+>', '', raw_summary).strip()
    excerpt = summary_text[:500] if summary_text else ""

    # Parse artist/album
    artist, album = parse_review_title(title)

    # Non-music filter
    if is_non_music(album, artist):
        print(f"  [SKIP non-music] {title}")
        continue

    # Determine type
    article_type = determine_type(title)

    # The Quietus does not publish numerical scores; use None
    score = None

    # For features: put title in album, column name in artist
    if article_type == "feature":
        # Column name detection
        if "Straight Hedge" in title:
            col_artist = "Straight Hedge (Noel Gardner)"
        elif "Album of the Week" in title:
            col_artist = "Album of the Week"
        elif "Reissue of the Week" in title:
            col_artist = "Reissue of the Week"
        elif "Live Album of the Week" in title:
            col_artist = "Live Album of the Week"
        else:
            col_artist = artist or "The Quietus"
        artist = col_artist
        album = title  # for features, put full title as album

    print(f"  [OK] type={article_type} | {title[:60]}")
    print(f"       artist={artist[:40]}, album={album[:40]}, score={score}")

    items.append({
        "album": album,
        "artist": artist,
        "score": score,
        "url": link,
        "source": "The Quietus",
        "pub_date": pub_date.isoformat() if pub_date else "",
        "tags": TAGS,
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": article_type
    })

print(f"\nTotal items: {len(items)}")

# -------------------------------------------------------------------
# 7. Write output
# -------------------------------------------------------------------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(items, f, indent=2, ensure_ascii=False)

print(f"Written to {OUTPUT_FILE}")

# Show final output
print("\n--- Final JSON ---")
print(json.dumps(items, indent=2, ensure_ascii=False)[:3000])
