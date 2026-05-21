import re, json, urllib.request
from datetime import datetime, timedelta

SITE_URL = "https://www.thewildcity.com"
DAYS_WINDOW = 3
CUTOFF = datetime.now() - timedelta(days=DAYS_WINDOW)
OUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-21/wild_city_reviews.json"
NON_MUSIC = ["BLU-RAY", "BLU RAY", "UHD", "VOD", "DVD"]

def is_music(album, artist):
    text = f"{album} {artist}".upper()
    return not any(k in text for k in NON_MUSIC)

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

def fetch(url_path, max_tries=3):
    """Fetch with retries, longer timeout"""
    for attempt in range(max_tries):
        try:
            req = urllib.request.Request(SITE_URL + url_path, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', errors='replace')
        except Exception as e:
            if attempt < max_tries - 1:
                import time
                time.sleep(2)
            else:
                raise e

# Parse all cached HTML files for items
import os
cached_files = {
    '/tmp/wildcity_home.html': '/',
    '/tmp/wildcity_features.html': '/features/',
    '/tmp/wildcity_news.html': '/news/',
}

all_items = {}  # href -> (date_str, date_obj)

pattern = re.compile(r'<a href="(/[^"?]+)"[^>]*class="box"[^>]*data-date="([^"]+)"')

for filepath, section in cached_files.items():
    if os.path.exists(filepath):
        with open(filepath, 'r', errors='replace') as f:
            html = f.read()
        for href, date_str in pattern.findall(html):
            if href not in all_items:
                d = parse_date(date_str)
                if d:
                    all_items[href] = (date_str, d)

print(f"Total unique items from cache: {len(all_items)}")

# Filter to recent
recent = [(href, ds, d) for href, (ds, d) in all_items.items() if d >= CUTOFF]
print(f"Recent items (>= {CUTOFF.date()}): {len(recent)}")
for href, ds, d in recent:
    print(f"  {ds}: {href}")

# Also scan page 2 of features/news to catch anything missed
for section, url_path in [('/features/', '/features/'), ('/news/', '/news/')]:
    try:
        html = fetch(f"{url_path}?page=2")
        for href, date_str in pattern.findall(html):
            if href not in all_items:
                d = parse_date(date_str)
                if d:
                    all_items[href] = (date_str, d)
    except Exception as e:
        print(f"  Page 2 error for {section}: {e}")

# Final recent filter
recent = [(href, ds, d) for href, (ds, d) in all_items.items() if d >= CUTOFF]
print(f"Total recent after page 2 scan: {len(recent)}")

results = []

for href, date_str, pub_date in sorted(recent, key=lambda x: x[2], reverse=True):
    try:
        full_url = SITE_URL + href
        article_html = fetch(href)

        # Title from og:title
        title_m = re.search(r'<meta property="og:title"[^>]*content="([^"]+)"', article_html)
        if not title_m:
            title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', article_html)
        title = ""
        if title_m:
            raw = title_m.group(1).strip()
            # decode HTML entities
            for ent in [('&#039;', "'"), ('&amp;', '&'), ('&#8217;', "'"), ('&#8216;', "'"),
                        ('&quot;', '"'), ('&lt;', '<'), ('&gt;', '>'), ('&nbsp;', ' ')]:
                raw = raw.replace(ent[0], ent[1])
            title = raw

        print(f"\nTitle: {title[:80]}")

        # Skip mixes
        if '/mixes/' in href:
            print(f"  SKIP - mix/audio show")
            continue

        # Parse artist/album from title
        artist, album = "", ""
        if ' - ' in title:
            parts = title.split(' - ', 1)
            artist = parts[0].strip()
            album = parts[1].strip()
        else:
            album = title

        # Remove "Review: " prefix
        album_lower = album.lower()
        for prefix in ["review: ", "review – ", "review — "]:
            if album_lower.startswith(prefix):
                album = album[len(prefix):].strip()
                break

        # Non-music filter
        if not is_music(album, artist):
            print(f"  SKIP non-music: {artist} - {album}")
            continue

        # Score
        score = None
        score_m = re.search(r'(\d+\.?\d*)\s*/\s*10', article_html)
        if score_m:
            score = float(score_m.group(1))
        print(f"  Artist: '{artist}', Album: '{album}', Score: {score}")

        # Excerpt
        excerpt = ""
        desc_m = re.search(r'<meta property="og:description"[^>]*content="([^"]+)"', article_html)
        if desc_m:
            raw_desc = desc_m.group(1).strip()
            for ent in [('&#039;', "'"), ('&amp;', '&'), ('&#8217;', "'"), ('&#8216;', "'"),
                        ('&quot;', '"'), ('&lt;', '<'), ('&gt;', '>'), ('&nbsp;', ' ')]:
                raw_desc = raw_desc.replace(ent[0], ent[1])
            excerpt = raw_desc[:500]
        print(f"  Excerpt: {excerpt[:100]}...")

        # Type
        rtype = "review" if '/review' in href.lower() else "feature"

        results.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": full_url,
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
    print(f"  {r['pub_date']}: {r['artist']} - {r['album']} [{r['type']}] {r['score']}")

with open(OUT_FILE, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nWritten to {OUT_FILE}")
