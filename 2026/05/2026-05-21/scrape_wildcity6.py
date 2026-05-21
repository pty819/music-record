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

def decode_html(text):
    for ent in [('&#039;', "'"), ('&amp;', '&'), ('&#8217;', "'"), ('&#8216;', "'"),
                ('&quot;', '"'), ('&lt;', '<'), ('&gt;', '>'), ('&nbsp;', ' ')]:
        text = text.replace(ent[0], ent[1])
    return text

def fetch(url_path, timeout=30):
    req = urllib.request.Request(SITE_URL + url_path, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

# Parse all cached HTML files for items
import os
cached_files = {
    '/tmp/wildcity_home.html': '/',
    '/tmp/wildcity_features.html': '/features/',
    '/tmp/wildcity_news.html': '/news/',
    '/tmp/wildcity_f2.html': '/features/?page=2',
}

all_items = {}  # href -> (date_str, date_obj)
pattern = re.compile(r'<a href="(/[^"?]+)"[^>]*class="box"[^>]*data-date="([^"]+)"')

for filepath in cached_files:
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
recent.sort(key=lambda x: x[2], reverse=True)
print(f"Recent items (>= {CUTOFF.date()}): {len(recent)}")
for href, ds, d in recent:
    print(f"  {ds}: {href}")

results = []

for href, date_str, pub_date in recent:
    if '/mixes/' in href:
        print(f"  SKIP mixes: {href}")
        continue

    try:
        article_html = fetch(href, timeout=20)

        # Title from og:title (most reliable)
        title_m = re.search(r'<meta property="og:title"[^>]*content="([^"]+)"', article_html)
        if not title_m:
            title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', article_html)
        title = ""
        if title_m:
            title = decode_html(title_m.group(1).strip())

        print(f"\nProcessing: {title[:60]}")

        # Parse artist/album from title: "Artist - Album" format
        artist, album = "", ""
        if ' - ' in title:
            parts = title.split(' - ', 1)
            artist = parts[0].strip()
            album = parts[1].strip()
        else:
            album = title

        # Remove "Review: " prefix from album
        album_lower = album.lower()
        for prefix in ["review: ", "review – ", "review — "]:
            if album_lower.startswith(prefix):
                album = album[len(prefix):].strip()
                break

        # Non-music filter
        if not is_music(album, artist):
            print(f"  SKIP non-music: {artist} - {album}")
            continue

        # Score - look for pattern like "8/10" or "8.5/10" near article content
        # NOT matching generic numbers on the page
        score = None
        # Try to find score in a more specific context
        score_m = re.search(r'<[^>]*>(\d+\.?\d*)\s*/\s*10\s*<[^>]*>', article_html)
        if not score_m:
            # Try meta description for score
            score_m = re.search(r'(\d+\.?\d*)\s*/\s*10', article_html[:5000])
        if score_m:
            s = float(score_m.group(1))
            if 0 <= s <= 10:
                score = s
                print(f"  Score: {score}")

        # Excerpt from og:description
        excerpt = ""
        desc_m = re.search(r'<meta property="og:description"[^>]*content="([^"]+)"', article_html)
        if desc_m:
            excerpt = decode_html(desc_m.group(1).strip())[:500]

        # Type
        rtype = "review" if '/review' in href.lower() else "feature"

        results.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": SITE_URL + href,
            "source": "wild_city",
            "pub_date": pub_date.strftime("%Y-%m-%d"),
            "tags": ["south asian", "alternative", "electronic"],
            "excerpt": excerpt,
            "site_id": "wild_city",
            "crawl_status": "success",
            "type": rtype
        })
        print(f"  Added: {artist} - {album} [{rtype}]")

    except Exception as e:
        print(f"  ERROR {href}: {e}")

print(f"\n=== Total results: {len(results)} ===")
for r in results:
    print(f"  {r['pub_date']}: {r['artist']} - {r['album']} [{r['type']}] score={r['score']}")

with open(OUT_FILE, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nWritten to {OUT_FILE}")
