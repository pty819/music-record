#!/usr/bin/env python3
"""Scrape Wild City for articles within 3-day window."""

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
    """Fetch URL with wget."""
    result = subprocess.run(
        ['wget', '-q', '-O', '-', '--timeout=15', '--user-agent=Mozilla/5.0', url],
        capture_output=True, text=True, timeout=20
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

def get_article_links():
    """Get all article links from homepage, news, features, mixes pages."""
    all_links = {}
    sections = [
        ('news', f'{BASE}/news'),
        ('features', f'{BASE}/features'),
        ('mixes', f'{BASE}/mixes'),
    ]
    
    for section, url in sections:
        print(f"Fetching {section} page...")
        html = wget(url)
        if not html:
            print(f"  Failed to fetch {url}")
            continue
        
        # Find all article links
        links = re.findall(r'href="(https://www\.thewildcity\.com/[^"]+)"', html)
        seen = set()
        for link in links:
            if link in seen:
                continue
            seen.add(link)
            # Filter to article pages only
            if ('/news/' in link or '/features/' in link or '/mixes/' in link) and \
               '/author/' not in link and '/tag/' not in link and '/page/' not in link:
                all_links[link] = section
        
        print(f"  Found {len(seen)} links in {section}")
    
    return all_links

def scrape_article(url, section):
    """Scrape individual article page."""
    html = wget(url)
    if not html:
        return None
    
    # Get title
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = strip_html(title_m.group(1)) if title_m else ''
    
    # Get date - look for <em>13 May 2026</em> pattern
    date_m = re.search(r'<em[^>]*>\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*</em>', html)
    pub_date = None
    if date_m:
        pub_date = parse_date(date_m.group(1))
    
    if not pub_date:
        return None
    
    # Check if within cutoff
    if pub_date < CUTOFF:
        return None
    
    # Get author from author links
    author = None
    author_m = re.search(r'<a[^>]+href=["\']/author/[^"\']+["\'][^>]*>\s*([^<]+)\s*</a>', html)
    if author_m:
        author = strip_html(author_m.group(1))
    
    # Get tags
    tags_match = re.findall(r'<a[^>]+href=["\']/tag/[^"\']+["\'][^>]*>\s*([^<]+)\s*</a>', html)
    tags = [strip_html(t) for t in tags_match] if tags_match else TAGS
    
    # Get excerpt - first paragraph after the date
    excerpt = ''
    if date_m:
        after = html[date_m.end():date_m.end()+3000]
        para_m = re.search(r'<p[^>]*>(.*?)</p>', after, re.DOTALL)
        if para_m:
            excerpt = strip_html(para_m.group(1))
    
    # Determine type and extract album/artist
    content_type = "feature"
    album = ""
    artist_val = author if author else ""
    score = None
    
    if title.startswith("Review:"):
        content_type = "review"
        rest = title.replace("Review:", "").strip()
        # Patterns: "Album Name by Artist" or "Artist – Album Name" or "Artist - Album Name"
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
            return None
    
    return {
        "album": album,
        "artist": artist_val,
        "score": score,
        "url": url,
        "source": BASE,
        "pub_date": pub_date.strftime("%Y-%m-%d"),
        "tags": tags if tags else TAGS,
        "excerpt": excerpt[:500],
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": content_type
    }

def main():
    print("=== Wild City Scraper ===")
    
    # Get all article links
    all_links = get_article_links()
    print(f"\nTotal unique article links found: {len(all_links)}")
    
    results = []
    for url, section in all_links.items():
        print(f"\nScraping [{section}]: {url}")
        article = scrape_article(url, section)
        if article:
            if article == "SKIP":
                print("  SKIPPED (outside window)")
            else:
                print(f"  Date: {article['pub_date']} | Type: {article['type']} | Title: {article.get('album', article.get('url', '')[:50])}")
                results.append(article)
        else:
            print("  Failed or no date")
        time.sleep(0.3)
    
    print(f"\n=== Results: {len(results)} articles within 3-day window ===")
    for r in results:
        print(f"  {r['pub_date']} [{r['type']}] {r.get('album', '')[:60]} - {r['url']}")
    
    # Write output
    output_path = "/home/liyifan/music-record/2026/05/2026-05-16/wild_city_reviews.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nWritten to {output_path}")

if __name__ == "__main__":
    main()