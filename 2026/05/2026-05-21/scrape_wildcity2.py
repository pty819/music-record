import sys, re, json
from html.parser import HTMLParser
import urllib.request
from datetime import datetime, timedelta

SITE_URL = "https://www.thewildcity.com"
DAYS_WINDOW = 3
CUTOFF = datetime.now() - timedelta(days=DAYS_WINDOW)
OUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-21/wild_city_reviews.json"
NON_MUSIC = ["BLU-RAY", "BLU RAY", "UHD", "VOD", "DVD"]

def is_music(album, artist):
    text = f"{album} {artist}".upper()
    return not any(k in text for k in NON_MUSIC)

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        href = d.get('href', '')
        if href:
            if any(x in href.lower() for x in ['review', 'article', 'feature', 'interview', 'podcast']):
                if href.startswith('/'):
                    href = SITE_URL + href
                self.links.append(href)

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='replace')

# Fetch homepage
html = fetch(SITE_URL + "/")
print(f"Fetched homepage: {len(html)} bytes")

# Parse links
p = LinkParser()
p.feed(html)
seen = set()
review_links = []
for l in p.links:
    if l not in seen:
        seen.add(l)
        review_links.append(l)

print(f"Found {len(review_links)} review links")
for l in review_links[:15]:
    print(f"  {l}")

# Check date pages
date_pattern = re.compile(r'data-date="(\d+/\d+/\d+)"')
matches = date_pattern.findall(html)
print(f"\nDates found on homepage: {matches[:10]}")

results = []

for url in review_links[:20]:
    try:
        print(f"\nFetching: {url}")
        article_html = fetch(url)

        # Extract date
        date_m = re.search(r'(\d+/\d+/\d+)', article_html[:3000])
        pub_date = None
        if date_m:
            try:
                pub_date = datetime.strptime(date_m.group(1), "%d/%m/%Y")
            except:
                try:
                    pub_date = datetime.strptime(date_m.group(1), "%m/%d/%Y")
                except:
                    pass
        print(f"  Date: {pub_date}")

        if pub_date and pub_date < CUTOFF:
            print(f"  SKIP - older than {DAYS_WINDOW} days")
            continue

        # Extract title
        title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', article_html)
        if not title_m:
            title_m = re.search(r'<h2[^>]*>([^<]+)</h2>', article_html)
        title = title_m.group(1).strip() if title_m else ""

        # Strip HTML tags
        title = re.sub(r'<[^>]+>', '', title)
        print(f"  Title: {title[:80]}")

        # Artist/Album
        parts = title.split(' - ', 1)
        if len(parts) == 2:
            artist, album = parts[0].strip(), parts[1].strip()
        else:
            artist, album = "", title

        # Check non-music
        if not is_music(album, artist):
            print(f"  SKIP non-music: {artist} - {album}")
            continue

        # Score
        score = None
        score_m = re.search(r'(\d+\.?\d*)\s*/\s*10', article_html)
        if score_m:
            score = float(score_m.group(1))
        print(f"  Artist: {artist}, Album: {album}, Score: {score}")

        # Excerpt
        content_m = re.search(r'class="entry-content"[^>]*>(.*?)</div>', article_html, re.DOTALL)
        if not content_m:
            content_m = re.search(r'class="post-content"[^>]*>(.*?)</div>', article_html, re.DOTALL)
        excerpt = ""
        if content_m:
            text = re.sub(r'<[^>]+>', ' ', content_m.group(1))
            excerpt = re.sub(r'\s+', ' ', text).strip()[:500]
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
            "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
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
    print(f"  {r['artist']} - {r['album']} ({r['pub_date']}) - {r['score']}")

with open(OUT_FILE, 'w') as f:
    json.dump(results, f, indent=2)
print(f"Written to {OUT_FILE}")
