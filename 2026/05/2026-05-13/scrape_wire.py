import urllib.request
import feedparser
import json
from datetime import datetime, timedelta

# Constants
SITE = "thewire"
SITE_ID = "the_wire"
TAGS = ["experimental", "avant-garde", "sound art", "improvisations"]
RSS_URL = "https://www.thewire.co.uk/audio/rss"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-13/the_wire_reviews.json"
DAYS = 7

# Calculate cutoff date
cutoff = datetime.now() - timedelta(days=DAYS)
print(f"Cutoff date: {cutoff}")

# Parse RSS
req = urllib.request.Request(RSS_URL, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=15) as resp:
    raw = resp.read().decode('utf-8', errors='replace')

feed = feedparser.parse(raw)
print(f"Total entries in feed: {len(feed.entries)}")

reviews = []
skipped_old = 0
skipped_non_review = 0

for entry in feed.entries:
    # Parse date
    pub_date_str = entry.get('published') or entry.get('updated', '')
    try:
        # Try common date formats
        pub_date = None
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%a, %d %b %Y %H:%M:%S', '%Y-%m-%d']:
            try:
                pub_date = datetime.strptime(pub_date_str[:len(fmt)+5] if len(pub_date_str) > len(fmt) else pub_date_str, fmt)
                break
            except:
                try:
                    from email.utils import parsedate_to_datetime
                    pub_date = parsedate_to_datetime(pub_date_str)
                    break
                except:
                    pass
        if pub_date is None:
            print(f"  Could not parse date: {pub_date_str} for {entry.get('title', '?')}")
            continue
    except Exception as e:
        print(f"  Date parse error ({pub_date_str}): {e}")
        continue

    # Filter by date
    if pub_date.tzinfo is not None:
        pub_date = pub_date.replace(tzinfo=None)
    
    if pub_date < cutoff:
        skipped_old += 1
        continue

    # Extract review data
    title = entry.get('title', '')
    link = entry.get('link', '')
    
    # Try to parse album/artist from title (usually "Album - Artist" format)
    album = ''
    artist = ''
    if ' - ' in title:
        parts = title.split(' - ', 1)
        album = parts[0].strip()
        artist = parts[1].strip() if len(parts) > 1 else ''
    
    # Look for description/summary as excerpt
    excerpt = ''
    if hasattr(entry, 'summary'):
        excerpt = entry.summary
    elif hasattr(entry, 'description'):
        excerpt = entry.description
    # Strip HTML tags from excerpt
    import re
    excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()
    
    # Try to extract score from excerpt or title
    score = None
    score_match = re.search(r'(\d+)/10', excerpt + ' ' + title)
    if score_match:
        score = int(score_match.group(1))
    
    review = {
        "album": album,
        "artist": artist,
        "score": score,
        "url": link,
        "source": "The Wire",
        "pub_date": pub_date.strftime('%Y-%m-%d') if pub_date else '',
        "tags": TAGS,
        "excerpt": excerpt[:500] if excerpt else '',
        "site_id": SITE_ID,
        "crawl_status": "success"
    }
    reviews.append(review)
    print(f"  [{pub_date.strftime('%Y-%m-%d')}] {album} - {artist} {f'({score}/10)' if score else '(no score)'}")

print(f"\nTotal reviews (last {DAYS} days): {len(reviews)}")
print(f"Skipped (too old): {skipped_old}")
print(f"Skipped (not review): {skipped_non_review}")

# Write output
with open(OUTPUT_FILE, 'w') as f:
    json.dump(reviews, f, indent=2, ensure_ascii=False)
print(f"\nWritten to: {OUTPUT_FILE}")

# Print summary
print(json.dumps({"site": SITE, "count": len(reviews), "days_scanned": str(DAYS)}, indent=2))