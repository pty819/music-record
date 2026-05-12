import urllib.request
import feedparser

# Try common RSS paths for The Wire
rss_urls = [
    'https://www.thewire.co.uk/audio/rss',
    'https://www.thewire.co.uk/feed',
    'https://www.thewire.co.uk/audio/feed',
    'https://www.thewire.co.uk/reviews/rss',
]

for url in rss_urls:
    print(f"\nTrying: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8', errors='replace')
            print(f"  Status: {resp.status}, Length: {len(content)}")
            print(f"  First 300: {content[:300]}")
    except Exception as e:
        print(f"  Error: {e}")

# Also try direct page
print("\n\nTrying main page: https://www.thewire.co.uk/audio")
try:
    req = urllib.request.Request('https://www.thewire.co.uk/audio', headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        content = resp.read().decode('utf-8', errors='replace')
        print(f"Status: {resp.status}, Length: {len(content)}")
        # Look for RSS links
        import re
        rss_links = re.findall(r'href=["\']([^"\']*rss[^"\']*)["\']', content, re.IGNORECASE)
        print(f"RSS links found: {rss_links}")
        atom_links = re.findall(r'href=["\']([^"\']*atom[^"\']*)["\']', content, re.IGNORECASE)
        print(f"Atom links found: {atom_links}")
except Exception as e:
    print(f"Error: {e}")