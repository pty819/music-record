import urllib.request
import feedparser
from datetime import datetime, timezone, timedelta
import json
import re

# Current timestamp
now_ts = datetime.now(timezone.utc).timestamp()
seven_days_ago_ts = now_ts - 7 * 24 * 3600

print(f"Current UTC: {datetime.now(timezone.utc)}")
print(f"7 days ago: {datetime.fromtimestamp(seven_days_ago_ts, timezone.utc)}")

feed_url = 'https://frootsmag.com/feed'
req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=15)
content = resp.read().decode('utf-8', errors='replace')

feed = feedparser.parse(content)
print(f"Total entries in feed: {len(feed.entries)}")

recent_entries = []
for entry in feed.entries:
    # Get publication date
    pub_date = None
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    
    if pub_date:
        pub_ts = pub_date.timestamp()
        print(f"  Entry: {entry.get('title', 'N/A')[:60]}, pub: {pub_date}, ts: {pub_ts:.0f}, within_7d: {pub_ts >= seven_days_ago_ts}")
        if pub_ts >= seven_days_ago_ts:
            recent_entries.append(entry)
    else:
        print(f"  Entry (no date): {entry.get('title', 'N/A')[:60]}")

print(f"\nRecent entries (last 7 days): {len(recent_entries)}")

# Now process recent entries
reviews = []
for entry in recent_entries:
    title = entry.get('title', '')
    link = entry.get('link', '')
    
    # Try to extract album/artist from title (common patterns: "Artist - Album" or "Album by Artist")
    album = ''
    artist = ''
    
    # Pattern: "Artist - Album"
    if ' - ' in title:
        parts = title.split(' - ', 1)
        artist = parts[0].strip()
        album = parts[1].strip()
    # Pattern: "Album by Artist"
    elif ' by ' in title.lower():
        match = re.search(r'(.+?)\s+by\s+(.+)', title, re.IGNORECASE)
        if match:
            album = match.group(1).strip()
            artist = match.group(2).strip()
    else:
        album = title
    
    # Get summary/excerpt
    summary = ''
    if hasattr(entry, 'summary'):
        summary = entry.summary
    elif hasattr(entry, 'description'):
        summary = entry.description
    # Strip HTML tags
    summary = re.sub(r'<[^>]+>', '', summary).strip()
    if len(summary) > 500:
        summary = summary[:500] + '...'
    
    # Publication date
    pub_date = None
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).strftime('%Y-%m-%d')
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc).strftime('%Y-%m-%d')
    
    # Score extraction (look for numbers in title or summary)
    score = None
    score_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:out\s*of\s*)?(?:\d+/|/|/)\s*\d+',
        r'(\d+(?:\.\d+)?)\s*(?:stars|pts?|points)',
        r'\[(\d+(?:\.\d+)?)\]',
    ]
    text_to_search = f"{title} {summary}"
    for pattern in score_patterns:
        m = re.search(pattern, text_to_search, re.IGNORECASE)
        if m:
            score = float(m.group(1))
            break
    
    review = {
        'album': album,
        'artist': artist,
        'score': score,
        'url': link,
        'source': 'fRoots',
        'pub_date': pub_date,
        'tags': 'folk, roots, world music',
        'excerpt': summary,
        'site_id': 'froots',
        'crawl_status': 'success'
    }
    reviews.append(review)
    print(f"  Review: album={album}, artist={artist}, score={score}, date={pub_date}")

print(f"\nTotal reviews extracted: {len(reviews)}")

# Write to JSON
output_path = '/home/liyifan/music-record/2026/05/2026-05-13/froots_reviews.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(reviews, f, ensure_ascii=False, indent=2)

print(f"Written to {output_path}")
print(f"Review count: {len(reviews)}")
