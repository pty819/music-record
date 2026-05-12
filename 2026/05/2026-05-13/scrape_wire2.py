import urllib.request
import feedparser
import json
from datetime import datetime, timedelta
import re

SITE = "thewire"
SITE_ID = "the_wire"
TAGS = ["experimental", "avant-garde", "sound art", "improvisations"]
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-13/the_wire_reviews.json"
DAYS = 7

cutoff = datetime.now() - timedelta(days=DAYS)

rss_urls = [
    'https://www.thewire.co.uk/audio/rss',
    'https://www.thewire.co.uk/writing/rss',
    'https://www.thewire.co.uk/reviews/rss',
]

all_entries = []
for url in rss_urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            feed = feedparser.parse(raw)
            if len(feed.entries) > 0:
                print(f"\n=== {url} === {len(feed.entries)} entries")
                all_entries.extend([(url, e) for e in feed.entries])
                e = feed.entries[0]
                print(f"First entry: {e.get('title', '')[:80]}")
                print(f"  Link: {e.get('link', '')}")
                print(f"  Published: {e.get('published', '')}")
    except Exception as ex:
        print(f"\n=== {url} === Error: {ex}")

print(f"\nTotal entries across all RSS feeds: {len(all_entries)}")

reviews = []
for rss_url, entry in all_entries:
    pub_date_str = entry.get('published', '')
    try:
        from email.utils import parsedate_to_datetime
        pub_date = parsedate_to_datetime(pub_date_str).replace(tzinfo=None)
    except:
        try:
            pub_date = datetime.strptime(pub_date_str[:25], '%a, %d %b %Y %H:%M:%S')
        except:
            pub_date = None
            print(f"  Could not parse date: {pub_date_str}")
    
    if pub_date and pub_date < cutoff:
        continue
    
    title = entry.get('title', '')
    link = entry.get('link', '')
    
    album = ''
    artist = ''
    if ' – ' in title:
        parts = title.split(' – ', 1)
        album = parts[0].strip()
        artist = parts[1].strip()
    elif ' - ' in title:
        parts = title.split(' - ', 1)
        album = parts[0].strip()
        artist = parts[1].strip()
    
    excerpt = re.sub(r'<[^>]+>', '', entry.get('summary', '')[:500])
    
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
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "success"
    }
    reviews.append(review)

print(f"\nTotal reviews (last {DAYS} days): {len(reviews)}")
for r in reviews:
    score_str = f"({r['score']}/10)" if r['score'] else "(no score)"
    print(f"  [{r['pub_date']}] {r['album']} - {r['artist']} {score_str}")

with open(OUTPUT_FILE, 'w') as f:
    json.dump(reviews, f, indent=2, ensure_ascii=False)
print(f"\nWritten to: {OUTPUT_FILE}")