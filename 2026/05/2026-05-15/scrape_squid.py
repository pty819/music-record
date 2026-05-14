#!/usr/bin/env python3
"""Find all May 2026 reviews by scanning recent newsIDs."""
import urllib.request
import ssl
import re
import json
from datetime import datetime, timedelta
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

def fetch(url, retries=2):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return None

CUTOFF = datetime(2026, 5, 12)
TODAY = datetime(2026, 5, 15)
TAGS = ['improvisation', 'jazz', 'experimental', 'electroacoustic']
SITE_ID = 'squids_ear'
NON_MUSIC_KEYWORDS = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']

def is_music_content(artist, album):
    text = f"{artist} {album}".upper()
    for kw in NON_MUSIC_KEYWORDS:
        if kw in text:
            return False
    return True

def parse_date(html):
    m = re.search(r'&nbsp;&nbsp;(\d{4}-\d{2}-\d{2})</font>', html)
    if m:
        try:
            return datetime.strptime(m.group(1), '%Y-%m-%d')
        except ValueError:
            pass
    m = re.search(r'on\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', html)
    if m:
        try:
            return datetime.strptime(m.group(0).lstrip('on '), '%B %d, %Y')
        except ValueError:
            pass
    m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', html)
    if m:
        try:
            return datetime.strptime(m.group(0), '%B %d, %Y')
        except ValueError:
            pass
    return None

def get_excerpt(html):
    patterns = [
        r'<b>Abstract</b>:(.*?)(?:<b>|</body>|<br\s*/?>)',
        r'<b>Abstract</b>(.*?)</p>',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1)
            clean = re.sub(r'<[^>]+>', ' ', raw)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if len(clean) > 20:
                return clean[:500]
    return ''

def get_review_info(news_id):
    url = f'https://www.squidco.com/cgi-bin/news/newsView.cgi?newsID={news_id}'
    html = fetch(url)
    if not html:
        return None, None, None

    # Extract title and artist from the page title: "Review: Artist - Title (Label)"
    title_m = re.search(r'<title>Review:\s*(.*?)\s*-\s*(.*?)\s*\(', html)
    artist = None
    title = None
    if title_m:
        artist = title_m.group(1).strip()
        title = title_m.group(2).strip()

    if not artist or not title:
        # Fallback: try the listing table
        artist_m = re.search(r"<tr><td><a[^>]*>([^<]+)</a></td><td><a[^>]*>([^<]+)</a></td>", html)
        if artist_m:
            artist = artist_m.group(1).strip()
            title = artist_m.group(2).strip()

    date = parse_date(html)
    excerpt = get_excerpt(html)
    has_score = bool(re.search(r'score|rating|out of|mark /|star', html, re.IGNORECASE))
    review_type = 'review' if has_score else 'feature'

    return {
        'album': title,
        'artist': artist,
        'score': None,
        'url': url,
        'source': "The Squid's Ear",
        'pub_date': date.strftime('%Y-%m-%d') if date else None,
        'tags': TAGS,
        'excerpt': excerpt,
        'site_id': SITE_ID,
        'crawl_status': 'ok',
        'type': review_type,
    }, date, artist

def main():
    # First, collect all May 2026 reviews by scanning recent newsIDs
    print('Scanning recent newsIDs for May 2026 reviews...')

    may_2026_ids = []
    # Scan newsIDs 2980 to 3020 to find all May 2026 entries
    for nid in range(2980, 3025):
        url = f'https://www.squidco.com/cgi-bin/news/newsView.cgi?newsID={nid}'
        html = fetch(url)
        if not html:
            continue

        # Check if this is a review page (has "Review:" in title)
        title_m = re.search(r'<title>(.*?)</title>', html)
        if not title_m or 'Review:' not in title_m.group(1):
            continue

        date = parse_date(html)
        if date and date.year == 2026 and date.month == 5:
            may_2026_ids.append((nid, date))
            print(f'  Found May 2026: newsID={nid} date={date.strftime("%Y-%m-%d")} title={title_m.group(1)[:60]}')
        elif date and date < CUTOFF:
            # We've gone past May 2026
            if nid > 3000:
                break

        time.sleep(0.2)

    print(f'\nFound {len(may_2026_ids)} May 2026 reviews')

    # Also check the blog page for any additional reviews
    print('\nChecking blog page for additional recent reviews...')
    blog_html = fetch('https://www.squidco.com/cgi-bin/news/newsView.cgi?newsID=1903')

    # Parse all links from the blog page using different patterns
    # The blog may use onclick handlers or different link formats
    # Let's look for URLs containing newsID

    # Try a broader pattern
    link_pat = r"newsID[=\"]+(\d+)"
    blog_links = re.findall(link_pat, blog_html)
    blog_review_ids = []
    for nid_str in blog_links:
        nid = int(nid_str)
        # Only include review pages (check date)
        url = f'https://www.squidco.com/cgi-bin/news/newsView.cgi?newsID={nid}'
        html = fetch(url)
        if not html:
            continue
        title_m = re.search(r'<title>(.*?)</title>', html)
        if title_m and 'Review:' in title_m.group(1):
            date = parse_date(html)
            if date and date.year == 2026 and date.month == 5:
                if nid not in [x[0] for x in may_2026_ids]:
                    may_2026_ids.append((nid, date))
                    print(f'  Blog found May 2026: newsID={nid} date={date.strftime("%Y-%m-%d")}')

    print(f'\nTotal May 2026 reviews: {len(may_2026_ids)}')

    # Now collect full data for each
    results = []
    for nid, date in may_2026_ids:
        if date < CUTOFF or date > TODAY:
            continue
        info, _, artist = get_review_info(nid)
        if info:
            # Check non-music filter
            if not is_music_content(info['artist'] or '', info['album'] or ''):
                print(f'  SKIP non-music: newsID={nid} {info["artist"]} - {info["album"]}')
                continue
            results.append(info)
            print(f'  OK: newsID={nid} {date.strftime("%Y-%m-%d")} {info["artist"][:40]} - {info["album"][:40]}')

    print(f'\nTotal items in range: {len(results)}')
    return results

if __name__ == '__main__':
    results = main()
    output_path = '/home/liyifan/music-record/2026/05/2026-05-15/squids_ear_reviews.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f'Written to {output_path}')
