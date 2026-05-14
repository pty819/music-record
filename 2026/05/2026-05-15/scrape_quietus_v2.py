#!/usr/bin/env python3
"""Scrape The Quietus reviews - v2"""
import json
import re
import sys
from datetime import datetime, timedelta

try:
    import feedparser
except ImportError:
    print("feedparser not installed, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser", "-q"])
    import feedparser

# Check RSS first
RSS_URL = "https://thequietus.com/columns/quietus-reviews/rss"
print(f"Checking RSS: {RSS_URL}")

feed = feedparser.parse(RSS_URL)
print(f"RSS status: {feed.status}")
print(f"Entries found: {len(feed.entries)}")

# Current date for filtering
now = datetime.now()
three_days_ago = now - timedelta(days=3)
print(f"Filtering for articles after: {three_days_ago.isoformat()}")

items = []
seen_urls = set()

for entry in feed.entries:
    pub_date = None
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        pub_date = datetime(*entry.published_parsed[:6])
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        pub_date = datetime(*entry.updated_parsed[:6])
    
    if not pub_date:
        print(f"  No date found for: {entry.get('title', 'Unknown')}")
        continue
    
    # Filter by 3 days
    if pub_date < three_days_ago:
        print(f"  Skipping (too old): {entry.title} - {pub_date}")
        continue
    
    url = entry.get('link', '')
    if not url:
        url = entry.get('id', '')
    
    # Skip if already seen
    if url in seen_urls:
        continue
    seen_urls.add(url)
    
    # Get full content from summary
    excerpt = ""
    if hasattr(entry, 'summary'):
        # feedparser summary is usually the full content in CDATA
        excerpt = entry.summary
        # Strip HTML
        excerpt = re.sub(r'<[^>]+>', '', excerpt)
        excerpt = excerpt.strip()[:500]
    
    title = entry.get('title', '')
    # Parse artist/album from title format: "Artist - Album" or just title
    artist = ""
    album = title
    if ' - ' in title:
        parts = title.split(' - ', 1)
        artist = parts[0].strip()
        album = parts[1].strip()
    
    item = {
        "album": album,
        "artist": artist,
        "score": None,  # Quietus doesn't use numerical scores
        "url": url,
        "source": "The Quietus",
        "pub_date": pub_date.isoformat(),
        "tags": ["experimental", "electronic", "jazz", "world", "psych", "prog", "free-improv"],
        "excerpt": excerpt,
        "site_id": "the_quietus",
        "crawl_status": "success",
        "type": "review"
    }
    items.append(item)
    print(f"  Added: {artist} - {album} ({pub_date})")

print(f"\nTotal items from RSS: {len(items)}")
print(json.dumps(items, indent=2, ensure_ascii=False))