#!/usr/bin/env python3
"""Scrape Sequenza21 via Camoufox browser"""

import sys
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/scripts')
import json
import re
from datetime import datetime, timedelta
from camoufox import Camoufox

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:500]

results = []
cutoff = datetime.now() - timedelta(days=3)
print(f"Cutoff: {cutoff}")

browser = Camoufox(headless=True, verbose=False)
page = browser.new_page()

try:
    # Navigate to main page
    resp = page.goto('https://www.sequenza21.com/', headers=HEADERS)
    print(f"Status: {resp.status}")
    page.wait_for_timeout(2000)
    
    # Click cookie accept if present
    try:
        accept_btn = page.locator('text=Accept').first
        if accept_btn.is_visible():
            accept_btn.click()
            print("Clicked Accept")
            page.wait_for_timeout(1000)
    except:
        pass
    
    # Get article list - look at first 2 pages max
    for page_num in range(1, 3):
        print(f"\n--- Page {page_num} ---")
        
        if page_num > 1:
            # Try to navigate to older page
            try:
                next_link = page.locator('a:has-text("Older")').first
                if next_link.is_visible():
                    next_link.click()
                    page.wait_for_timeout(2000)
                    print(f"Navigated to older posts page {page_num}")
                else:
                    print("No more older posts link")
                    break
            except Exception as e:
                print(f"Could not navigate to page {page_num}: {e}")
                break
        
        articles = page.locator('article, .post, .entry').all()
        print(f"Found {len(articles)} articles on page {page_num}")
        
        if not articles:
            print("No articles found, trying alternate selectors")
            articles = page.locator('h2 a, h3 a').all()
            print(f"Found {len(articles)} headline links")
        
        for article in articles:
            try:
                title_el = article.locator('h2, h3, .title').first
                title = title_el.inner_text()
                link_el = article.locator('a').first
                url = link_el.get_attribute('href') if link_el else ''
                
                if not url or 'sequenza21' not in url:
                    continue
                
                # pub date
                date_el = article.locator('time, .date, .published').first
                date_str = date_el.inner_text() if date_el else ''
                try:
                    pub_date = datetime.strptime(date_str.strip(), '%b %d, %Y')
                except:
                    pub_date = datetime.now()
                
                if pub_date < cutoff:
                    print(f"SKIP (old): {pub_date} - {title[:40]}")
                    continue
                
                # Check non-music filter
                if any(x in title.lower() for x in ['blu-ray', 'uhd', 'vod', 'dvd']):
                    print(f"SKIP (non-music): {title}")
                    continue
                
                # Get excerpt
                excerpt_el = article.locator('.excerpt, .summary, .entry-summary, p').first
                excerpt = strip_html(excerpt_el.inner_text()) if excerpt_el else ''
                
                # Artist/album from title
                album = title
                artist = ''
                if ' - ' in title:
                    parts = title.split(' - ', 1)
                    artist = parts[0].strip()
                    album = parts[1].strip()
                
                item = {
                    "album": album,
                    "artist": artist,
                    "score": None,
                    "url": url,
                    "source": "sequenza21.com",
                    "pub_date": pub_date.strftime('%Y-%m-%d'),
                    "tags": [],
                    "excerpt": excerpt[:500],
                    "site_id": "sequenza21",
                    "crawl_status": "success",
                    "type": "review"
                }
                results.append(item)
                print(f"OK: {pub_date} {artist} - {album[:40]}")
                
            except Exception as e:
                print(f"Error parsing article: {e}")
        
        # Check if we went too far (all old content)
        if page_num > 1:
            break  # Only scan 2 pages max per rules
            
finally:
    browser.close()

print(f"\nTotal: {len(results)}")
with open('/home/liyifan/music-record/2026/05/2026-05-24/sequenza21_reviews.json', 'w') as f:
    json.dump(results, f, indent=2)
print("Written to sequenza21_reviews.json")