import re, json
from datetime import datetime, timedelta
from html.parser import HTMLParser

SITE_URL = "https://www.thewildcity.com"
DAYS_WINDOW = 3
CUTOFF = datetime.now() - timedelta(days=DAYS_WINDOW)
OUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-21/wild_city_reviews.json"
NON_MUSIC = ["BLU-RAY", "BLU RAY", "UHD", "VOD", "DVD"]

def is_music(album, artist):
    text = f"{album} {artist}".upper()
    return not any(k in text for k in NON_MUSIC)

def parse_date(date_str):
    """Parse dd/mm/yyyy format"""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

# Read homepage HTML
with open("/tmp/wildcity_home.html", "r", errors="replace") as f:
    html = f.read()

print(f"Read {len(html)} bytes")

# Find all data-date attributes and their associated links
# Pattern: <a href="URL" class="box" data-date="DD/MM/YYYY">
pattern = re.compile(r'<a href="([^"]+)"[^>]*class="box"[^>]*data-date="([^"]+)"')
matches = list(pattern.findall(html))
print(f"Found {len(matches)} items with dates")

# Filter to recent items
recent_items = []
for url, date_str in matches:
    d = parse_date(date_str)
    if d and d >= CUTOFF:
        recent_items.append((url, date_str, d))
    elif d:
        print(f"  OLD: {url} ({date_str})")

print(f"\nRecent items ({DAYS_WINDOW} days): {len(recent_items)}")
for url, date_str, d in recent_items:
    print(f"  {date_str}: {url}")

# Now fetch each recent article
import urllib.request

def fetch_article(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='replace')

results = []
seen_urls = set()

for url, date_str, pub_date in recent_items:
    if url in seen_urls:
        continue
    seen_urls.add(url)
    
    try:
        print(f"\nFetching: {url}")
        article_html = fetch_article(url)
        
        # Extract title
        title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', article_html)
        if not title_m:
            title_m = re.search(r'<h2[^>]*>([^<]+)</h2>', article_html)
        title = ""
        if title_m:
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        print(f"  Title: {title[:80]}")
        
        # Artist/Album from title
        parts = title.split(' - ', 1)
        if len(parts) == 2:
            artist, album = parts[0].strip(), parts[1].strip()
        else:
            artist, album = "", title
        
        # Remove "Review: " prefix from album
        if album.lower().startswith("review:"):
            album = album[7:].strip()
        if artist.lower().startswith("review:"):
            artist = artist[7:].strip()
        
        # Non-music filter
        if not is_music(album, artist):
            print(f"  SKIP non-music: {artist} - {album}")
            continue
        
        # Score
        score = None
        score_m = re.search(r'(\d+\.?\d*)\s*/\s*10', article_html)
        if score_m:
            score = float(score_m.group(1))
        
        # Excerpt - get first 500 chars of article content
        excerpt = ""
        content_m = re.search(r'class="entry-content"[^>]*>(.*?)</div>', article_html, re.DOTALL)
        if not content_m:
            content_m = re.search(r'class="post-content"[^>]*>(.*?)</div>', article_html, re.DOTALL)
        if content_m:
            text = re.sub(r'<[^>]+>', ' ', content_m.group(1))
            excerpt = re.sub(r'\s+', ' ', text).strip()[:500]
        print(f"  Artist: {artist}, Album: {album}, Score: {score}")
        print(f"  Excerpt: {excerpt[:100]}...")
        
        # Type
        is_feature = any(x in url.lower() for x in ['feature', 'interview', 'podcast'])
        rtype = "feature" if is_feature else "review"
        
        results.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": "wild_city",
            "pub_date": pub_date.strftime("%Y-%m-%d"),
            "tags": ["south asian", "alternative", "electronic"],
            "excerpt": excerpt,
            "site_id": "wild_city",
            "crawl_status": "success",
            "type": rtype
        })
    except Exception as e:
        print(f"  ERROR: {e}")

print(f"\n=== Total results: {len(results)} ===")
for r in results:
    print(f"  {r['pub_date']}: {r['artist']} - {r['album']} ({r['type']}) - {r['score']}")

with open(OUT_FILE, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nWritten to {OUT_FILE}")
