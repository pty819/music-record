import requests
from bs4 import BeautifulSoup
import json
import re

URLS = [
    "https://acloserlisten.com/2026/05/12/lawrence-english-werner-dafeldecker-fathom-tides/",
    "https://acloserlisten.com/2026/05/11/shhe-thalassa/",
    "https://acloserlisten.com/2026/05/10/matteo-stella-radeche-fonne/",
    "https://acloserlisten.com/2026/05/09/ptastvo-the-grit/",
    "https://acloserlisten.com/2026/05/08/anastasia-kristensen-bestarium-sombre/",
    "https://acloserlisten.com/2026/05/07/hwxxng-k-core/",
    "https://acloserlisten.com/2026/05/06/kreng-wormhole/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

results = []

for url in URLS:
    print(f"\nFetching: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        title = soup.find('h1', class_='entry-title') or soup.find('h1')
        title_text = title.get_text(strip=True) if title else ''
        print(f"  Title: {title_text}")

        # Extract album and artist from title (format: "Artist ~ Album")
        album = ''
        artist = ''
        if '~' in title_text:
            parts = title_text.split('~')
            artist = parts[0].strip()
            album = parts[1].strip()
        elif '-' in title_text:
            parts = title_text.split('-')
            artist = parts[0].strip()
            album = parts[1].strip() if len(parts) > 1 else ''

        # Look for score
        score = None
        score_text = ''
        # Check common score locations
        for el in soup.find_all(string=re.compile(r'\d+/10|\d+\s*out\s*of\s*10|score', re.I)):
            parent = el.parent
            if parent:
                score_text = parent.get_text(strip=True)
                m = re.search(r'(\d+(?:\.\d+)?)\s*(?:/|out of)\s*10', score_text, re.I)
                if m:
                    score = float(m.group(1))
                    break
                m = re.search(r'^(\d+(?:\.\d+)?)$', score_text.strip())
                if m:
                    val = float(m.group(1))
                    if val <= 10:
                        score = val
                        break

        # If no score found in text, look for a dedicated score element
        if score is None:
            for el in soup.find_all(class_=re.compile(r'score|rating|rank', re.I)):
                t = el.get_text(strip=True)
                m = re.search(r'(\d+(?:\.\d+)?)', t)
                if m:
                    val = float(m.group(1))
                    if val <= 10:
                        score = val
                        score_text = t
                        break

        print(f"  Artist: {artist}, Album: {album}, Score: {score}")

        # Get pub_date
        pub_date = ''
        time_el = soup.find('time')
        if time_el:
            pub_date = time_el.get('datetime', '')[:10]
        if not pub_date:
            meta = soup.find('meta', attrs={'property': 'article:published_time'})
            if meta:
                pub_date = meta.get('content', '')[:10]

        # Get excerpt/content
        excerpt = ''
        for p in soup.find_all('p'):
            t = p.get_text(strip=True)
            if len(t) > 50 and not t.startswith('<'):
                excerpt = t
                break

        # Get tags
        tags = []
        for tag in soup.find_all('a', class_=re.compile(r'tag')):
            tags.append(tag.get_text(strip=True))

        results.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": "A Closer Listen",
            "pub_date": pub_date,
            "tags": tags,
            "excerpt": excerpt[:500] if excerpt else '',
            "site_id": "a_closer_listen",
            "crawl_status": "success"
        })

    except Exception as ex:
        print(f"  ERROR: {ex}")
        results.append({
            "album": "",
            "artist": "",
            "score": None,
            "url": url,
            "source": "A Closer Listen",
            "pub_date": "",
            "tags": [],
            "excerpt": "",
            "site_id": "a_closer_listen",
            "crawl_status": f"error: {ex}"
        })

print(f"\n\nTotal scraped: {len(results)}")
with open('/home/liyifan/music-record/2026/05/2026-05-12/a_closer_listen_reviews.json', 'w') as f:
    json.dump(results, f, indent=2)
print("Written to a_closer_listen_reviews.json")
