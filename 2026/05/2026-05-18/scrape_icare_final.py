#!/usr/bin/env python3
"""
Scrape I CARE IF YOU LISTEN
Strategy: RSS (feedparser) for 3-day window items
"""

import json
import re
import feedparser
from datetime import datetime, date, timezone
from email.utils import parsedate_to_datetime
import sys

# ── Config ──────────────────────────────────────────────────────────────────
RSS_URL = "https://icareifyoulisten.com/feed"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-18/icareifyoulisten_reviews.json"
SITE_ID = "icareifyoulisten"
TAGS = ["contemporary classical", "new music", "living music"]
CUTOFF_DATE = date(2026, 5, 14)  # articles on or after May 14

# ── Helpers ──────────────────────────────────────────────────────────────────

def parse_pub_date(pub_date_str):
    try:
        return parsedate_to_datetime(pub_date_str)
    except:
        return None

def strip_html(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', str(text))
    clean = clean.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
    clean = clean.replace('&#8216;', "'").replace('&#8217;', "'").replace('&#8230;', '...')
    clean = clean.replace('&#039;', "'").replace('&lt;', '<').replace('&gt;', '>')
    return clean.strip()

def clean_excerpt(excerpt):
    """Remove 'Continued', 'The post X appeared first on Y' cruft"""
    # Remove "Continued" link text
    excerpt = re.sub(r'\s*Continued\s*', ' ', excerpt)
    # Remove "The post X appeared first on Y" footer
    excerpt = re.sub(r"\s*The post .+? appeared first on .+?\.\s*$", '', excerpt, flags=re.IGNORECASE)
    return excerpt.strip()

def in_3day_window(pub_date_str):
    dt = parse_pub_date(pub_date_str)
    if dt is None:
        return False
    return dt.date() >= CUTOFF_DATE

def detect_type(category, title, tags):
    """Determine if article is 'review' or 'feature'"""
    cat_lower = category.lower()
    title_lower = title.lower()
    non_review = ['interview', 'playlist', 'video', 'essay']
    if any(nr in cat_lower for nr in non_review):
        return "feature"
    review_cats = ['album', 'concert', 'performance', 'recording']
    if any(rc in cat_lower for rc in review_cats):
        return "review"
    return "review"  # default to review for music articles

def detect_non_music(items_text):
    """Check if article is about DVD/Blu-ray/film (not music)"""
    markers = ['blu-ray', 'blu ray', 'uhd', 'vod', 'dvd', 'film', 'movie', 'documentary']
    text = items_text.lower()
    return any(m in text for m in markers)

# ── Main scrape ───────────────────────────────────────────────────────────────

print("=== I CARE IF YOU LISTEN Scraper ===")
print(f"Cutoff: {CUTOFF_DATE}")

# Step 1: Parse RSS
feed = feedparser.parse(RSS_URL)
print(f"Total RSS items: {len(feed.entries)}")

recent_items = []
for e in feed.entries:
    pub = e.get('published', '')
    if in_3day_window(pub):
        recent_items.append(e)
        dt = parse_pub_date(pub)
        print(f"  IN WINDOW: {dt.date()} - {e.title[:60]}")

print(f"Items in 3-day window: {len(recent_items)}")

# No items in window? Output empty array
if not recent_items:
    print("No articles in 3-day window. Writing empty array.")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump([], f)
    print(f"Output: {OUTPUT_FILE}")
    sys.exit(0)

# Step 2: Process each item
results = []
for e in recent_items:
    pub = e.get('published', '')
    dt = parse_pub_date(pub)
    tags = [t.term for t in e.get('tags', [])]
    category = tags[0] if tags else 'Unknown'
    title = e.title
    author = e.get('author', e.get('dc_creator', 'Unknown'))

    # Get full content from summary (CDATA with HTML)
    summary = e.get('summary') or e.get('description') or ''
    raw_excerpt = strip_html(summary)
    excerpt = clean_excerpt(raw_excerpt)
    if len(excerpt) > 500:
        excerpt = excerpt[:500].rsplit(' ', 1)[0] + '...'

    # Check non-music filter
    check_text = f"{title} {excerpt}"
    if detect_non_music(check_text):
        print(f"  SKIP (non-music): {title[:50]}")
        continue

    # Determine type
    article_type = detect_type(category, title, tags)

    # Extract album name from title if present (for album reviews)
    # Patterns: "Album Name is a..." or "Artist's 'Album Name' is..."
    album = None
    m = re.search(r"'([^']+)'(?:\s+is|\s+are)", title)
    if m:
        album = m.group(1)
    elif article_type == "review" and "album" in category.lower():
        # For album reviews without quoted name, use the article title minus common suffixes
        album = title

    # For concert/festival reviews - festival name becomes the "album"
    if article_type == "review" and album is None:
        festival_match = re.search(r'Dig That Treasure!|Manchester Collective|Rewire|Borealis', title)
        if festival_match:
            album = festival_match.group(0)

    # Extract pub_date in ISO format
    pub_date_iso = dt.isoformat() if dt else None

    item = {
        "album": album,
        "artist": author,
        "score": None,
        "url": e.link,
        "source": "I CARE IF YOU LISTEN",
        "pub_date": pub_date_iso,
        "tags": TAGS + tags[:5],
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "ok",
        "type": article_type,
    }
    results.append(item)
    print(f"  Added [{article_type}]: {title[:50]}")
    print(f"    album={album}, artist={author}")

print(f"\nTotal items after filtering: {len(results)}")

# Step 3: Write output
with open(OUTPUT_FILE, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"Output written to: {OUTPUT_FILE}")
print(f"Count: {len(results)}")