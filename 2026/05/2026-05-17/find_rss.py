#!/usr/bin/env python3
import subprocess, re

def get_page_via_curl(url):
    result = subprocess.run([
        'curl', '-s', '--max-time', '20', '-L', '-A',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        url
    ], capture_output=True, text=True)
    return result.stdout

# Get the main reviews page and find feed URLs
html = get_page_via_curl('https://thequietus.com/columns/quietus-reviews/')
# Find feed links
feed_links = re.findall(r'<link[^>]+type="application/rss\+xml"[^>]*>', html)
feed_links += re.findall(r'<link[^>]+type="application/atom\+xml"[^>]*>', html)
print("Feed links:", feed_links[:10])

# Also find any href with /feed or /rss
feed_hrefs = re.findall(r'href="([^"]*(?:feed|rss|atom)[^"]*)"', html, re.IGNORECASE)
print("Feed hrefs:", feed_hrefs[:10])

# Let's try some common feed URLs
for url in [
    'https://thequietus.com/columns/quietus-reviews/feed/',
    'https://thequietus.com/feed/',
    'https://thequietus.com/quietus-reviews/feed/',
    'https://thequietus.com/columns/quietus-reviews/rss/',
]:
    text = get_page_via_curl(url)
    print(f"\n{url} -> len={len(text)}, has<item>={('<item>' in text)}")
    if '<item>' in text:
        print("  Found <item>!")
        print(text[:500])