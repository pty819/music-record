#!/usr/bin/env python3
"""Scrape Wild City for articles within 3-day window."""

import urllib.request
import json
import re
from datetime import datetime, timedelta
import ssl

# Setup
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE = "https://www.thewildcity.com"
CUTOFF = datetime(2026, 5, 13)  # 3 days ago
TODAY = datetime(2026, 5, 16)
SITE_ID = "wild_city"
TAGS = ["south asian", "alternative", "electronic"]

def parse_date(date_str):
    """Parse date like '13 May 2026'"""
    date_str = date_str.strip()
    # Try "13 May 2026" format
    m = re.match(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', date_str)
    if m:
        day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month_map = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                     'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
        month = month_map.get(month_str[:3], 0)
        if month:
            return datetime(year, month, day)
    return None

def get_page(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def extract_article_data(html, url):
    """Extract article metadata from HTML page."""
    # Extract title
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ''
    
    # Extract date - look for "13 May 2026" style
    date_m = re.search(r'<em[^>]*>\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*</em>', html)
    if not date_m:
        date_m = re.search(r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})', html)
    
    pub_date = None
    if date_m:
        pub_date = parse_date(date_m.group(1))
    
    # Extract author from author link or meta
    author_m = re.search(r'<a[^>]+href=["\']/author/[^"\']+["\'][^>]*>([^<]+)</a>', html)
    if not author_m:
        author_m = re.search(r'author["\s:>]+([^<]+)', html, re.IGNORECASE)
    author = author_m.group(1).strip() if author_m else None
    
    # Extract tags
    tags = []
    tag_matches = re.findall(r'<a[^>]+href=["\']/tag/[^"\']+["\'][^>]*>([^<]+)</a>', html)
    tags = [t.strip() for t in tag_matches if t.strip()]
    
    # Extract excerpt/summary from first paragraph after date
    excerpt = ''
    if date_m:
        after_date = html[date_m.end():date_m.end()+2000]
        para_m = re.search(r'<p[^>]*>(.*?)</p>', after_date, re.DOTALL)
        if para_m:
            excerpt = re.sub(r'<[^>]+>', '', para_m.group(1)).strip()
            excerpt = re.sub(r'\s+', ' ', excerpt)
    
    # Determine type: if "Review:" prefix -> "review", else "feature"
    content_type = "feature"
    score = None
    album = ""
    artist = ""
    
    if title.startswith("Review:"):
        content_type = "review"
        # Try to extract album/artist from title: "Review: Album Name by Artist" or "Review: Artist - Album Name"
        rest = title.replace("Review:", "").strip()
        if " by " in rest:
            parts = rest.split(" by ", 1)
            album = parts[0].strip()
            artist = parts[1].strip()
        elif " – " in rest:
            parts = rest.split(" – ", 1)
            artist = parts[0].strip()
            album = parts[1].strip()
        elif " - " in rest:
            parts = rest.split(" - ", 1)
            artist = parts[0].strip()
            album = parts[1].strip()
        else:
            # For reviews like "Review: RANJ Finds A Friend In Swaggering Rhythms On Debut Mixtape '27 CLUB'"
            album = rest
    
    # Check for non-music filter keywords
    skip_keywords = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    full_text = (album + ' ' + artist + ' ' + title).upper()
    for kw in skip_keywords:
        if kw.upper() in full_text:
            return None
    
    return {
        "album": album,
        "artist": artist,
        "score": score,
        "url": url,
        "source": BASE,
        "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else None,
        "tags": tags if tags else TAGS,
        "excerpt": excerpt[:500] if excerpt else '',
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": content_type
    }

def main():
    results = []
    
    # Article URLs from homepage sections (News, Features, Mixes)
    # Based on browser visit, these are the recent articles:
    article_urls = [
        # News
        "https://www.thewildcity.com/news/21654-yung-singh-launches-label-ekta-with-new-single-nug46",
        "https://www.thewildcity.com/news/21637-arooj-aftab-kr-na-natasha-noorani-jorja-smith-more-come-together-for-riz-ahmed-s-bait",
        "https://www.thewildcity.com/news/21599-champak-introduce-themselves-as-the-new-alt-rock-band-on-the-block-with-feed-the-clown",
        "https://www.thewildcity.com/news/21587-sick-industry-debut-ep-rust-in-the-economy",
        "https://www.thewildcity.com/news/21585-somnium-monkey-double-ep-vettam-butterfly-effect",
        "https://www.thewildcity.com/news/21574-kerala-s-tribemama-marykali-returns-after-three-years-with-scorpio-moon",
        "https://www.thewildcity.com/news/21575-inspired-by-goa-sunsplash-djazz-blurs-dub-breakbeats-and-techno-on-new-ep",
        "https://www.thewildcity.com/news/21562-yash-locusts-new-album-nirvana",
        # Need to get remaining news URLs
    ]
    
    # Actually let me get all URLs from the listing pages
    # The homepage shows articles, let me fetch the listing pages
    for section in ['news', 'features']:
        url = f"{BASE}/{section}"
        print(f"Fetching {url}...")
        html = get_page(url)
        if html:
            # Find all article URLs
            urls = re.findall(r'href=["\'](https://www\.thewildcity\.com/[^"\']+)["\']', html)
            # Dedupe
            seen = set()
            for u in urls:
                if u not in seen and not any(x in u for x in ['/author/', '/tag/', '/page/', '/category/']):
                    seen.add(u)
            print(f"  Found {len(seen)} article URLs")
            for u in list(seen)[:20]:
                print(f"  - {u}")
    
    print("\n---")
    # Now fetch individual articles to get dates
    articles_to_check = [
        ("https://www.thewildcity.com/news/21654-yung-singh-launches-label-ekta-with-new-single-nug46", "news"),
        ("https://www.thewildcity.com/news/21637-arooj-aftab-kr-na-natasha-noorani-jorja-smith-more-come-together-for-riz-ahmed-s-bait", "news"),
    ]
    
    for url, section in articles_to_check:
        html = get_page(url)
        if html:
            data = extract_article_data(html, url)
            if data:
                print(f"\nURL: {url}")
                print(f"  Title patterns: {re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL).group(1)[:80] if re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL) else 'not found'}")
                print(f"  Date found: {data['pub_date']}")
                print(f"  Type: {data['type']}")
    
    print(f"\nTotal results: {len(results)}")

if __name__ == "__main__":
    main()