import urllib.request
import re
import json
from datetime import datetime, timedelta

SITE = "the_wire"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-13/the_wire_reviews.json"
DAYS = 7
TAGS = ["experimental", "avant-garde", "sound art", "improvisations"]

cutoff = datetime.now() - timedelta(days=DAYS)

# Fetch the essays index
req = urllib.request.Request(
    'https://www.thewire.co.uk/in-writing/essays/',
    headers={'User-Agent': 'Mozilla/5.0'}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    content = resp.read().decode('utf-8', errors='replace')

# Find all "-reviewed" links (album/music reviews are essays with this suffix)
all_reviewed = re.findall(r'href=["\'](https?://www\.thewire\.co\.uk/in-writing/essays/[^"\']+-reviewed[^"\']*)["\']', content, re.IGNORECASE)
all_reviewed = list(dict.fromkeys(all_reviewed))
print(f"Found {len(all_reviewed)} '-reviewed' essay links")

reviews = []
for url in all_reviewed:
    req2 = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            article_content = resp2.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"  Skipping {url}: {e}")
        continue

    # Extract date from article
    date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', article_content)
    if not date_match:
        print(f"  No date found for {url}")
        continue

    try:
        pub_date = datetime.strptime(date_match.group(1), '%d %B %Y')
    except ValueError:
        try:
            pub_date = datetime.strptime(date_match.group(1), '%d %b %Y')
        except ValueError:
            print(f"  Could not parse date: {date_match.group(1)} for {url}")
            continue

    if pub_date < cutoff:
        print(f"  Skipping old review: {url} ({pub_date.strftime('%Y-%m-%d')})")
        continue

    # Extract title
    title_match = re.search(r'<title>\s*["\']?([^<"\']+)["\']?\s*</title>', article_content)
    if not title_match:
        title_match = re.search(r'<title>([^<]+)</title>', article_content)
    title = title_match.group(1).strip() if title_match else ''
    title = re.sub(r'\s*-\s*The Wire\s*$', '', title).strip()

    # Parse "Artist: Album reviewed" or '"Quote": Artist reviewed'
    # Examples:
    #   "Battered but persisting hope": Hen Ogledd reviewed
    #   One of the great living saxophonists: Jean-Luc Guionnet reviewed
    album = ''
    artist = ''
    # Try to extract from title
    if ': ' in title:
        parts = title.split(': ', 1)
        # First part might be a quote (album name) or just intro
        potential_album = parts[0].strip().strip('"')
        potential_artist = parts[1].strip().replace(' reviewed', '').strip()
        if potential_artist and len(potential_artist) < 100:
            artist = potential_artist
            album = potential_album
    elif ' reviewed' in title:
        remainder = title.replace(' reviewed', '')
        # Usually "Artist - Album" or just "Artist"
        if ' – ' in remainder:
            parts = remainder.split(' – ', 1)
            album = parts[0].strip()
            artist = parts[1].strip()
        elif ' - ' in remainder:
            parts = remainder.split(' - ', 1)
            album = parts[0].strip()
            artist = parts[1].strip()
        else:
            artist = remainder

    # Extract excerpt (first paragraph of article body)
    body_match = re.search(r'<div[^>]*class=["\'][^"\']*body[^"\']*["\'][^>]*>(.*?)</div>', article_content, re.DOTALL)
    if not body_match:
        body_match = re.search(r'<article[^>]*>(.*?)</article>', article_content, re.DOTALL)
    excerpt = ''
    if body_match:
        raw = body_match.group(1)
        # Strip tags
        clean = re.sub(r'<[^>]+>', ' ', raw)
        clean = re.sub(r'\s+', ' ', clean).strip()
        excerpt = clean[:500]

    # Try to extract score
    score = None
    score_match = re.search(r'(\d+)\s*/\s*10', excerpt + ' ' + title)
    if score_match:
        score = int(score_match.group(1))

    review = {
        "album": album,
        "artist": artist,
        "score": score,
        "url": url,
        "source": "The Wire",
        "pub_date": pub_date.strftime('%Y-%m-%d'),
        "tags": TAGS,
        "excerpt": excerpt,
        "site_id": SITE,
        "crawl_status": "success"
    }
    reviews.append(review)
    score_str = f"({score}/10)" if score else "(no score)"
    print(f"  [{pub_date.strftime('%Y-%m-%d')}] {album} - {artist} {score_str}")

print(f"\nTotal reviews (last {DAYS} days): {len(reviews)}")

with open(OUTPUT_FILE, 'w') as f:
    json.dump(reviews, f, indent=2, ensure_ascii=False)
print(f"Written to: {OUTPUT_FILE}")
