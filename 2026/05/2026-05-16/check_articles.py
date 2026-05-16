#!/usr/bin/env python3
"""Scrape Wild City - check dates for articles found on homepage."""

import subprocess
import re
import json
import time
from datetime import datetime
from html import unescape

BASE = "https://www.thewildcity.com"
CUTOFF = datetime(2026, 5, 13)
TODAY = datetime(2026, 5, 16)
SITE_ID = "wild_city"
TAGS = ["south asian", "alternative", "electronic"]

def wget(url):
    result = subprocess.run(
        ['wget', '-q', '-O', '-', '--timeout=12', '--user-agent=Mozilla/5.0', url],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout

def parse_date(s):
    m = re.match(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s.strip())
    if m:
        mo = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}.get(m.group(2).lower()[:3], 0)
        if mo:
            return datetime(int(m.group(3)), mo, int(m.group(1)))
    return None

def strip_html(s):
    s = re.sub(r'<[^>]+>', ' ', s)
    s = unescape(s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

# URLs from homepage (extracted via browser JS)
articles = [
    "https://www.thewildcity.com/news/21675-nash-steps-into-a-producer-s-role-with-a-remix-for-nina-las-vegas",
    "https://www.thewildcity.com/news/21664-khokkosh-doesn-t-flinch-from-distilling-unease-into-leftfield-pop-on-freeuse-org",
    "https://www.thewildcity.com/news/21661-that-boy-roby-set-out-to-mix-haryanvi-ragini-with-dub-end-up-with-a-psych-rock-jam",
    "https://www.thewildcity.com/news/21658-rajah-betta-flips-classic-ad-jingles-south-asian-cultural-memory-for-the-club-on-offcuts",
    "https://www.thewildcity.com/features/21576-review-ranj-finds-a-friend-in-swaggering-rhythms-on-debut-mixtape-27-club",
    "https://www.thewildcity.com/features/21586-revisiting-women-in-electronic-music-the-role-of-ableton-in-shaping-new-voices",
    # Mixes are not music reviews, skip them
]

results = []
for url in articles:
    print(f"\nFetching: {url}")
    html = wget(url)
    if not html:
        print("  FAILED to fetch")
        continue
    
    # Get title
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = strip_html(title_m.group(1)) if title_m else ''
    
    # Get date - <em>13 May 2026</em>
    date_m = re.search(r'<em[^>]*>\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*</em>', html)
    pub_date = None
    if date_m:
        pub_date = parse_date(date_m.group(1))
        print(f"  Date: {date_m.group(1)} -> {pub_date}")
    else:
        print(f"  No date found")
    
    # Get author
    author_m = re.search(r'<a[^>]+href=["\']/author/[^"\']+["\'][^>]*>\s*([^<]+)\s*</a>', html)
    author = strip_html(author_m.group(1)) if author_m else ''
    
    # Get excerpt
    excerpt = ''
    if date_m:
        after = html[date_m.end():date_m.end()+3000]
        para_m = re.search(r'<p[^>]*>(.*?)</p>', after, re.DOTALL)
        if para_m:
            excerpt = strip_html(para_m.group(1))
    
    # Determine type
    content_type = "feature"
    album = ""
    artist_val = author
    score = None
    
    if title.startswith("Review:"):
        content_type = "review"
        rest = title.replace("Review:", "").strip()
        if " by " in rest:
            parts = rest.split(" by ", 1)
            album = parts[0].strip()
            artist_val = parts[1].strip()
        elif " – " in rest:
            parts = rest.split(" – ", 1)
            artist_val = parts[0].strip()
            album = parts[1].strip()
        elif " - " in rest:
            parts = rest.split(" - ", 1)
            artist_val = parts[0].strip()
            album = parts[1].strip()
        else:
            album = rest
    
    # Non-music filter
    skip_keywords = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    check_text = (album + ' ' + artist_val + ' ' + title).upper()
    for kw in skip_keywords:
        if kw.upper() in check_text:
            print(f"  SKIPPED (non-music: {kw})")
            continue
    
    if pub_date and pub_date >= CUTOFF:
        print(f"  >>> WITHIN WINDOW")
        results.append({
            "album": album,
            "artist": artist_val,
            "score": score,
            "url": url,
            "source": BASE,
            "pub_date": pub_date.strftime("%Y-%m-%d"),
            "tags": TAGS,
            "excerpt": excerpt[:500],
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": content_type
        })
    elif pub_date:
        print(f"  >>> OUTSIDE window")
    else:
        print(f"  >>> No date")
    
    print(f"  Title: {title[:80]}")
    time.sleep(0.5)

print(f"\n=== Results: {len(results)} articles within window ===")
for r in results:
    print(f"  {r['pub_date']} [{r['type']}] {r.get('album','')[:60]} - {r['url']}")

output_path = "/home/liyifan/music-record/2026/05/2026-05-16/wild_city_reviews.json"
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nWritten to {output_path}")