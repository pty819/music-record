import feedparser
import sys

# Check for common RSS paths
urls = [
    'https://rootsworld.com/rw/feed/',
    'https://rootsworld.com/feed/',
    'https://rootsworld.com/rss/',
    'https://rootsworld.com/rw/rss/',
]

for url in urls:
    try:
        d = feedparser.parse(url)
        if d.entries:
            print(f'RSS found at {url}: {len(d.entries)} entries')
            for entry in d.entries[:3]:
                title = entry.get('title') or 'no title'
                print(f'  - {str(title)[:60]}')
        else:
            print(f'{url}: no entries')
    except Exception as e:
        print(f'{url}: error - {e}')