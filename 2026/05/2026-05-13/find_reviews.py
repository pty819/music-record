import urllib.request
import re

# Check thewire.co.uk for review sections
urls_to_check = [
    'https://www.thewire.co.uk/reviews',
    'https://www.thewire.co.uk/reviews/albums',
    'https://www.thewire.co.uk/music',
    'https://www.thewire.co.uk/latest-reviews',
]

headers = {'User-Agent': 'Mozilla/5.0'}

for url in urls_to_check:
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8', errors='replace')
            print(f"\n=== {url} === Status: {resp.status}")
            # Look for review links
            review_links = re.findall(r'href=["\'](https?://www\.thewire\.co\.uk[^"\']*(?:review|album)[^"\']*)["\']', content, re.IGNORECASE)
            print(f"Review links (first 10): {review_links[:10]}")
            # Also find section headers/nav
            nav = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', content)
            relevant_nav = [(h, t) for h, t in nav if any(k in h.lower() for k in ['review', 'album', 'music', 'audio', 'latest'])]
            print(f"Relevant nav: {relevant_nav[:15]}")
    except Exception as e:
        print(f"\n=== {url} === Error: {e}")