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

def fetch(url):
    req = urllib.request.Request(SITE_URL + url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='replace')

# Fetch section pages
pages_to_scan = ["/features/", "/news/", "/mixes/"]
all_items = {}  # url -> (date_str, date_obj)

for page in pages_to_scan:
    for page_num in range(1, 4):
        url = page if page_num == 1 else f"{page}?page={page_num}"
        try:
            html = fetch(url)
            pattern = re.compile(r'<a href="(/[^"]+)"[^>]*class="box"[^>]*data-date="([^"]+)"')
            for href, date_str in pattern.findall(html):
                d = parse_date(date_str)
                if href not in all_items and d:
                    all_items[href] = (date_str, d)
            # Check if there's pagination
            if f"?page={page_num+1}" not in html:
                break
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            break

print(f"Total items found: {len(all_items)}")

# Filter to recent (within window)
recent = [(href, ds, d) for href, (ds, d) in all_items.items() if d >= CUTOFF]
print(f"Recent items: {len(recent)}")
for href, ds, d in recent:
    print(f"  {ds}: {href}")

results = []

for href, date_str, pub_date in recent:
    try:
        full_url = SITE_URL + href
        req = urllib.request.Request(full_url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            article_html = r.read().decode('utf-8', errors='replace')

        # Title from og:title or h1
        title_m = re.search(r'<meta property="og:title"[^>]*content="([^"]+)"', article_html)
        if not title_m:
            title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', article_html)
        title = ""
        if title_m:
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            title = title.replace('&#039;', "'").replace('&amp;', '&').replace('&#8217;', "'")

        print(f"\nTitle: {title[:80]}")
        print(f"URL: {full_url}")

        # Determine type: mixes are not reviews
        is_mix = '/mixes/' in href
        is_review = '/review' in href.lower() and not is_mix
        is_feature_type = any(x in href for x in ['/features/', '/interview', '/news/']) and not is_mix

        if is_mix:
            print(f"  SKIP - mix/audio show")
            continue

        # Parse artist - album from title
        artist, album = "", ""
        if ' - ' in title:
            parts = title.split(' - ', 1)
            artist = parts[0].strip()
            album = parts[1].strip()
        else:
            album = title

        # Remove "Review: " prefix
        if album.lower().startswith("review:"):
            album = album[7:].strip()

        # Non-music filter
        if not is_music(album, artist):
            print(f"  SKIP non-music: {artist} - {album}")
            continue

        # Score
        score = None
        score_m = re.search(r'(\d+\.?\d*)\s*/\s*10', article_html)
        if score_m:
            score = float(score_m.group(1))
        print(f"  Artist: {artist}, Album: {album}, Score: {score}")

        # Excerpt from og:description or content
        excerpt = ""
        desc_m = re.search(r'<meta property="og:description"[^>]*content="([^"]+)"', article_html)
        if desc_m:
            excerpt = desc_m.group(1).strip()[:500]
        else:
            content_m = re.search(r'class="entry-content"[^>]*>(.*?)</div>', article_html, re.DOTALL)
            if content_m:
                text = re.sub(r'<[^>]+>', ' ', content_m.group(1))
                excerpt = re.sub(r'\s+', ' ', text).strip()[:500]

        rtype = "review" if is_review else "feature"
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
        print(f"  Added as {rtype}")

    except Exception as e:
        print(f"  ERROR: {e}")

print(f"\n=== Total results: {len(results)} ===")
for r in results:
    print(f"  {r['pub_date']}: {r['artist']} - {r['album']} [{r['type']}] {r['score']}")

with open(OUT_FILE, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nWritten to {OUT_FILE}")
