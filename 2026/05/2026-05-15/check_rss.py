import feedparser
import urllib.request
import ssl

# Try RSS feed
rss_urls = [
    'https://www.squidco.com/ear/feed/',
    'https://www.squidco.com/ear/rss/',
    'https://www.squidco.com/feed/',
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

found = False
for url in rss_urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            content = resp.read().decode('utf-8', errors='replace')
            print(f'RSS found at {url}: {len(content)} bytes')
            print(content[:800])
            found = True
            break
    except Exception as e:
        print(f'Failed {url}: {e}')

if not found:
    print('No RSS feed found at common paths')
