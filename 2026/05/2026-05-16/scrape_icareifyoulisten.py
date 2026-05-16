#!/usr/bin/env python3
"""
Scrape I CARE IF YOU LISTEN - comprehensive browser-based scraping
Window: last 3 days (May 13-16, 2026)
"""
import feedparser
import re
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import sys

sys.path.insert(0, '/home/liyifan/music-record/2026/05/2026-05-16')

CUTOFF = datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc)
TODAY = datetime(2026, 5, 16, 23, 59, 59, tzinfo=timezone.utc)
SITE_ID = "icareifyoulisten"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-16/icareifyoulisten_reviews.json"

RSS_URL = "https://icareifyoulisten.com/feed"
TAGS = ["contemporary classical", "new music", "living music"]

# Article type patterns in categories
REVIEW_CATS = ['album', 'cd']

# HTML entity map
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

def decode_entities(text):
    """Decode common HTML entities."""
    for entity, char in ENTITIES.items():
        text = text.replace(entity, char)
    return text

def strip_html(html_str):
    """Strip HTML tags from string."""
    if not html_str:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_str)
    # Decode entities
    text = decode_entities(text)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_excerpt(raw_text):
    """Clean RSS excerpt text."""
    if not raw_text:
        return ""
    text = raw_text
    # Decode HTML entities first (before stripping tags)
    for entity, char in ENTITIES.items():
        text = text.replace(entity, char)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove "Continued The post X appeared first on..." cruft
    text = re.sub(r'\s*…?\s*Continued\s+The post.*?appeared first on.*?I CARE IF YOU LISTEN\.?\s*$',
                  '…', text, flags=re.IGNORECASE)
    text = text.strip()
    if len(text) > 500:
        text = text[:500].rsplit(' ', 1)[0] + '…'
    return text

def parse_article_type(categories):
    """Determine if article is a review or feature based on category tags."""
    category_text = ' '.join([c.term.lower() for c in categories])
    if any(cat in category_text for cat in REVIEW_CATS):
        return "review"
    return "feature"

def main():
    print("Fetching RSS feed...")
    feed = feedparser.parse(RSS_URL)
    print(f"Total RSS entries: {len(feed.entries)}")
    
    results = []
    
    # First pass: collect all entries within window from RSS
    window_entries = []
    for i, entry in enumerate(feed.entries):
        pub_date_str = entry.get("published", "")
        if not pub_date_str:
            continue
        try:
            dt = parsedate_to_datetime(pub_date_str)
        except Exception:
            continue
        
        if dt < CUTOFF or dt > TODAY:
            continue
        
        window_entries.append((i, entry, dt))
    
    print(f"Entries in 3-day window: {len(window_entries)}")
    
    for i, entry, dt in window_entries:
        categories = entry.get("tags", [])
        article_type = parse_article_type(categories)
        
        # Extract artist from categories (first non-generic category)
        generic_cats = {'album', 'cd', 'concert', 'interview', 'playlist', 'premiere', 'essay', 'video', 'videos', 'interviews', 'concerts', 'albums', 'essays', 'listn up'}
        artist_cats = [c.term for c in categories if c.term.lower() not in generic_cats]
        artist = artist_cats[0] if artist_cats else ""
        
        # For features/interviews, the "album" is the article title
        album = entry.title
        
        url = entry.link
        
        # Extract excerpt - use summary_detail if available
        summary_detail = entry.get("summary_detail", {})
        raw_summary = summary_detail.get("value", "") or entry.get("summary", "") or ""
        excerpt = clean_excerpt(raw_summary)
        
        record = {
            "album": album,
            "artist": artist,
            "score": None,  # features don't have scores
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
        print(f"  [{article_type}] {entry.title[:60]} | artist={artist}")
    
    print(f"\nTotal items in window: {len(results)}")
    reviews = [r for r in results if r['type'] == 'review']
    features = [r for r in results if r['type'] == 'feature']
    print(f"Reviews: {len(reviews)}, Features: {len(features)}")
    
    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Written to {OUTPUT_FILE}")
    
    # Print detailed results
    for r in results:
        print(f"\n=== {r['type'].upper()} ===")
        print(f"Title: {r['album']}")
        print(f"Artist: {r['artist']}")
        print(f"Score: {r['score']}")
        print(f"URL: {r['url']}")
        print(f"PubDate: {r['pub_date']}")
        print(f"Excerpt: {r['excerpt'][:200]}...")
    
    return results

if __name__ == "__main__":
    main()