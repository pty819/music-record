import urllib.request
import feedparser

# Try common RSS paths
urls = [
    'https://frootsmag.com/feed',
    'https://frootsmag.com/rss',
    'https://frootsmag.com/reviews/feed',
    'https://frootsmag.com/articles/feed',
]
for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        content = resp.read().decode('utf-8', errors='replace')
        if 'rss' in content[:500].lower() or 'feed' in content[:500].lower():
            print(f'RSS FOUND: {url}')
            print(content[:500])
            break
        else:
            print(f'No RSS at {url}')
    except Exception as e:
        print(f'Error {url}: {e}')
