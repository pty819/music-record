#!/usr/bin/env python3
"""Scrape Bandcamp Daily - extracts reviews and features from RSS feed."""

import feedparser
from datetime import datetime, timezone, timedelta
import re
import json

WORKSPACE = '/home/liyifan/music-record/2026/05/2026-05-15'
OUTPUT_FILE = f'{WORKSPACE}/bandcamp_daily_reviews.json'
CUTOFF_DAYS = 3
SITE_ID = 'bandcamp_daily'
TAGS = ['experimental', 'electronic', 'world', 'ambient', 'scene-specific']
NON_MUSIC_KEYWORDS = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']

today = datetime.now(timezone.utc).date()
cutoff = today - timedelta(days=CUTOFF_DAYS)

def parse_rss_date(published_str):
    from email.utils import parsedate_to_datetime
    return parsedate_to_datetime(published_str)

def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_non_music(artist, album):
    combined = f"{artist} {album}".upper()
    return any(kw.upper() in combined for kw in NON_MUSIC_KEYWORDS)

def parse_article_type(url, tags):
    url_lower = url.lower()
    tag_names = [t['term'].lower() for t in tags]
    if 'album-of-the-day' in url_lower:
        return 'review'
    elif any(x in url_lower for x in ['label-profile', 'lists', 'features', 'big-ups', 'scene-report']):
        return 'feature'
    return 'feature'

def parse_review_title(title):
    """Parse artist/album from review title. Handles Unicode curly quotes."""
    # Use \u201c and \u201d for curly double quotes
    quote_chars = '\u201c\u201d"\'"'
    pattern = r'^(.+?),\s*[' + quote_chars + r'](.+?)[' + quote_chars + r']\s*$'
    m = re.match(pattern, title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return '', title

def extract_review_data(e, pub_date):
    url = e.get('link', '')
    title = e.get('title', '')
    summary = e.get('summary', '')

    excerpt = strip_html(summary)
    if len(excerpt) > 500:
        excerpt = excerpt[:500].rsplit(' ', 1)[0] + '...'

    article_type = parse_article_type(url, e.get('tags', []))

    artist = ''
    album = ''

    if article_type == 'review':
        artist, album = parse_review_title(title)
    else:
        album = title

    if is_non_music(artist, album):
        return None

    pub_dt = parse_rss_date(e.published)
    pub_date_str = pub_dt.strftime('%Y-%m-%d')

    return {
        'album': album,
        'artist': artist,
        'score': None,
        'url': url,
        'source': 'Bandcamp Daily',
        'pub_date': pub_date_str,
        'tags': TAGS,
        'excerpt': excerpt,
        'site_id': SITE_ID,
        'crawl_status': 'success',
        'type': article_type,
    }

# --- Parse RSS ---
feed = feedparser.parse('/tmp/bandcamp_feed.xml')
print(f"Total RSS entries: {len(feed.entries)}")

in_range = []
for e in feed.entries:
    try:
        pub_dt = parse_rss_date(e.published)
        pub_date = pub_dt.date()
        if cutoff <= pub_date <= today:
            in_range.append((e, pub_date))
        elif pub_date < cutoff:
            break
    except Exception as ex:
        print(f"  Date parse error: {e.get('title','')} -> {ex}")

print(f"In range ({cutoff} to {today}): {len(in_range)}")

items = []
skipped_non_music = 0
for e, pub_date in in_range:
    data = extract_review_data(e, pub_date)
    if data is None:
        skipped_non_music += 1
        print(f"  SKIPPED (non-music): {e['title'][:60]}")
        continue
    items.append(data)
    type_marker = 'R' if data['type'] == 'review' else 'F'
    print(f"  [{type_marker}] {pub_date} | {data['artist'][:25]:25s} | {data['album'][:50]}")

print(f"\nTotal: {len(items)} items, {skipped_non_music} non-music skipped")

with open(OUTPUT_FILE, 'w') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)
print(f"Written: {OUTPUT_FILE}")
