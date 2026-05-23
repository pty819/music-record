#!/usr/bin/env python3
import subprocess
import sys
import re
import html
import json
import os
from datetime import datetime, timezone, timedelta

# Add feedparser path
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.12/site-packages')
import feedparser

CUTOFF = datetime.now(timezone.utc) - timedelta(days=3)
RSS_URL = 'https://www.side-line.com/feed/'
OUTPUT = '/home/liyifan/music-record/2026/05/2026-05-24/side_line_reviews.json'

def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_entry(entry):
    title = entry.title
    
    # Get full content
    content_html = ''
    if 'content' in entry and entry.content:
        content_html = entry.content[0].get('value', '')
    elif 'summary' in entry:
        content_html = entry.summary
    
    excerpt = strip_html(content_html)[:500] if content_html else ''
    
    text_lower = (title + ' ' + excerpt).lower()
    
    # Filter: skip non-music video formats
    if any(x in text_lower for x in ['(blu-ray)', '(uhd)', '(vod)', '(dvd)']):
        return None
    
    # Determine type
    the_type = 'review'
    if any(kw in text_lower for kw in ['interview', 'exclusive', 'featured']):
        the_type = 'feature'
    elif any(kw in text_lower for kw in ['tracklist', 'track list', 'tracklisting']):
        the_type = 'tracklist'
    
    # Try to extract artist/album from title
    parts = re.split(r'\s*[-–|]\s*', title)
    artist = ''
    album = ''
    if len(parts) >= 2:
        artist = parts[0].strip()
        album = parts[-1].strip()
        for suffix in ['review', 'single', 'ep', 'album', 'video', 'stream']:
            album = re.sub(rf'\s+{suffix}$', '', album, flags=re.IGNORECASE)
    
    return {
        'album': album,
        'artist': artist,
        'score': None,
        'url': entry.link,
        'source': 'side-line.com',
        'pub_date': entry.get('published', ''),
        'tags': [],
        'excerpt': excerpt,
        'site_id': 'side_line',
        'crawl_status': 'success',
        'type': the_type
    }

def main():
    print(f"Fetching RSS: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)
    print(f"Total entries: {len(feed.entries)}")
    print(f"Cutoff: {CUTOFF}")
    
    items = []
    skipped = 0
    
    for entry in feed.entries:
        pub = entry.get('published', '')
        try:
            from email.utils import parsedate_to_datetime
            pub_dt = parsedate_to_datetime(pub)
            if pub_dt < CUTOFF:
                continue
        except Exception as e:
            print(f"Date parse error on '{pub}': {e}")
            pass
        
        result = parse_entry(entry)
        if result is None:
            skipped += 1
            continue
        items.append(result)
    
    print(f"\nWithin 3-day window: {len(items)}")
    print(f"Skipped (filtered): {skipped}")
    
    for item in items:
        print(f"  [{item['type']}] {item['artist']} - {item['album']}")
        print(f"    url: {item['url']}")
        print(f"    pub: {item['pub_date']}")
        print(f"    excerpt: {item['excerpt'][:80]}...")
    
    # Write output
    with open(OUTPUT, 'w') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(items)} items to {OUTPUT}")
    
    return len(items)

if __name__ == '__main__':
    count = main()