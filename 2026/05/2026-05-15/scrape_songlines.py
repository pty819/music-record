#!/usr/bin/env python3
"""Scrape Songlines reviews hub."""
import urllib.request
import ssl
import re
import json
from datetime import datetime, timedelta

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

BASE_URL = 'https://www.songlines.co.uk'
REVIEWS_URL = f'{BASE_URL}/reviews-hub'
OUT_FILE = '/home/liyifan/music-record/2026/05/2026-05-15/songlines_reviews.json'

CUTOFF = datetime.now() - timedelta(days=3)

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=REQ_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  Fetch error {url}: {e}')
        return None

def parse_review_date(date_str):
    date_str = date_str.strip()
    for fmt in ['%B %d, %Y', '%B/%Y', '%b/%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return None

def star_rating_to_score(stars_str):
    if not stars_str:
        return None
    filled = stars_str.count('★')
    empty = stars_str.count('☆')
    total = filled + empty
    if total == 0:
        return None
    return round(filled / total * 10, 1)

def extract_review_from_page(url, html):
    # Album title from h1
    m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    album = m.group(1).strip() if m else None

    # Rating
    m = re.search(r'Rating:\s*(★+)', html)
    rating_str = m.group(1) if m else None
    score = star_rating_to_score(rating_str)

    # Author
    m = re.search(r'Author:\s*</strong>\s*([^\n<]+)', html)
    if not m:
        m = re.search(r'Author:\s*([^\n<]+)', html)
    author = m.group(1).strip() if m else None

    # Review date
    m = re.search(r'Magazine Review Date:\s*([A-Za-z]+/?/?[0-9]+)', html)
    date_str = m.group(1).strip() if m else None
    pub_date = None
    if date_str:
        pub_dt = parse_review_date(date_str)
        if pub_dt:
            pub_date = pub_dt.strftime('%Y-%m-%d')

    # Excerpt - text after h2
    m = re.search(r'<h2[^>]*>.*?</h2>(.*?)<div', html, re.DOTALL)
    excerpt = None
    if m:
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        excerpt = text[:500].strip() if text else None

    return {
        'album': album,
        'author': author,
        'score': score,
        'pub_date': pub_date,
        'excerpt': excerpt,
    }

def main():
    print(f'Fetching {REVIEWS_URL}...')
    html = fetch(REVIEWS_URL)
    if not html:
        print('Failed to fetch listing page')
        with open(OUT_FILE, 'w') as f:
            json.dump([], f)
        return

    print(f'Listing page HTML length: {len(html)}')

    # Find all review links
    review_links = re.findall(r'href="(review/[^"]+)"', html)
    unique_links = list(dict.fromkeys(review_links))  # preserve order, remove dupes
    print(f'Found {len(unique_links)} review links: {unique_links[:10]}')

    items = []
    for i, link in enumerate(unique_links):
        url = f'{BASE_URL}/{link}'
        print(f'  [{i+1}/{len(unique_links)}] Visiting {url}...')

        page_html = fetch(url)
        if not page_html:
            continue

        data = extract_review_from_page(url, page_html)
        print(f'    album={data["album"]}, date={data["pub_date"]}, score={data["score"]}')

        # Check date
        if data['pub_date']:
            try:
                pub_dt = datetime.strptime(data['pub_date'], '%Y-%m-%d')
                if pub_dt < CUTOFF:
                    print(f'    SKIP: {data["pub_date"]} is older than 3 days')
                    continue
            except:
                pass

        # Non-music filter
        album = data.get('album') or ''
        artist = data.get('artist') or ''
        skip_keywords = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
        if any(k in album.upper() or k in artist.upper() for k in skip_keywords):
            print(f'    SKIP: non-music (Blu-ray/DVD)')
            continue

        item = {
            'album': data.get('album'),
            'artist': data.get('artist'),
            'score': data.get('score'),
            'url': url,
            'source': 'songlines',
            'pub_date': data.get('pub_date'),
            'tags': ['world music', 'folk', 'global music'],
            'excerpt': data.get('excerpt'),
            'site_id': 'songlines',
            'crawl_status': 'ok',
            'type': 'review',
        }
        items.append(item)
        print(f'    -> ADDED')

        if len(items) >= 30:
            print('  (capping at 30 items)')
            break

    print(f'\nTotal items: {len(items)}')
    with open(OUT_FILE, 'w') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f'Written to {OUT_FILE}')

if __name__ == '__main__':
    main()
