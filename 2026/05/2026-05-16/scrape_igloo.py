#!/usr/bin/env python3
"""Final scrape of Igloo Magazine: reviews + check breaking news for recent features."""

import json
import re
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

BASE_DATE = datetime(2026, 5, 16)
CUTOFF = BASE_DATE - timedelta(days=3)
SITE_ID = "igloo_magazine"
SOURCE = "Igloo Magazine"
TAGS = ["experimental electronic", "IDM", "ambient", "glitch", "electroacoustic"]
OUTPUT_FILE = '/home/liyifan/music-record/2026/05/2026-05-16/igloo_magazine_reviews.json'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except:
        return None


def extract_score(content):
    patterns = [
        r'(\d+\.?\d?)\s*/\s*10',
        r'[★✦✯⯃⯪]?\s*(\d+\.?\d?)\s*(?:out of\s*10)',
        r'[Ss]core[:\s]+(\d+\.?\d?)',
        r'Rating[:\s]+(\d+\.?\d?)',
    ]
    for p in patterns:
        m = re.search(p, content)
        if m:
            return float(m.group(1))
    return None


def parse_heading(heading):
    if '::' in heading:
        parts = heading.split('::', 1)
        artist = parts[0].strip()
        rest = parts[1].strip()
        special_tag = None
        tag_match = re.search(r'—\s*\[([^\]]+)\]', rest)
        if tag_match:
            special_tag = tag_match.group(1)
            rest = rest[:tag_match.start()].strip()
        label_match = re.search(r'\(([^)]+)\)\s*$', rest)
        album = rest
        label = None
        if label_match:
            label = label_match.group(1)
            album = rest[:label_match.start()].strip()
        return artist, album, label, special_tag
    return heading, None, None, None


def is_non_music(artist, album):
    keywords = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD', 'Blu-ray']
    text = (artist or '') + ' ' + (album or '')
    return any(kw in text for kw in keywords)


def scrape_review(url, heading, date_str, author, *categories):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            return None, 'not_found'
        if resp.status_code >= 500:
            return None, 'server_error'
        soup = BeautifulSoup(resp.text, 'html.parser')
        h1 = soup.find('h1')
        if h1 and re.search(r'Error 404|404|Nothing Found', h1.get_text(), re.I):
            return None, 'not_found'

        article = soup.find('article') or soup.find('main')
        body_text = article.get_text(separator=' ', strip=True) if article else ''
        excerpt = body_text[:500].strip() if body_text else ''
        score = extract_score(body_text)

        artist, album, label, special_tag = parse_heading(heading)

        if special_tag or 'profile' in [c.lower() for c in categories]:
            item_type = 'feature'
        else:
            item_type = 'review'

        pub_date = parse_date(date_str)
        if pub_date:
            parsed = datetime.strptime(pub_date, "%Y-%m-%d")
            if parsed < CUTOFF:
                return None, 'outside_window'

        if is_non_music(artist, album):
            return None, 'non_music'

        return {
            "album": album or heading,
            "artist": artist or '',
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": TAGS,
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": item_type,
        }, 'success'
    except Exception as e:
        return None, f'error: {e}'


def main():
    # Reviews within 3-day window (May 13-16, 2026)
    # Only 3 review articles fall within the window on igloomag.com
    review_items = [
        # These are all from /category/reviews, page 1
        ("Burial Grid :: NORD Compendium (Spinal Constellation)", "https://igloomag.com/reviews/burial-grid-nord-compendium", "05/15/2026", "Don Haugen", "Reviews"),
        ("Yakuza Jacuzzi :: Wabi-Sabi (Cyclical Dreams)", "https://igloomag.com/reviews/yakuza-jacuzzi-wabi-sabi-cyclical-dreams", "05/15/2026", "Will Wonks", "Reviews"),
        ("Neuro… No Neuro :: MemLoss (Audiobulb)", "https://igloomag.com/reviews/neuro-no-neuro-memloss-audiobulb", "05/14/2026", "J. Batista", "Reviews"),
    ]

    results = []
    for heading, url, date_str, author, *cats in review_items:
        pub_date = parse_date(date_str)
        if pub_date:
            parsed = datetime.strptime(pub_date, "%Y-%m-%d")
            if parsed < CUTOFF:
                print(f"SKIP (outside window): {heading} ({date_str})")
                continue

        print(f"Scraping: {heading} ({date_str})")
        item, status = scrape_review(url, heading, date_str, author, *cats)
        if item:
            results.append(item)
            print(f"  -> OK: type={item['type']}, score={item['score']}, album={item['album'][:40]}")
            print(f"     excerpt: {item['excerpt'][:120]}...")
        else:
            print(f"  -> {status}: {heading}")

    print(f"\nTotal: {len(results)} items")

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Written to {OUTPUT_FILE}")
    for r in results:
        print(f"  {r['pub_date']} | {r['type']:7s} | {r['artist']} - {r['album'][:50]}")


if __name__ == '__main__':
    main()