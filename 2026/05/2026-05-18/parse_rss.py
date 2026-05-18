import feedparser
import urllib.request
import ssl
from datetime import datetime, timedelta
import re

# Create SSL context
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# The RSS feed at /rss
rss_url = 'https://www.thewire.co.uk/rss'

req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
    content = response.read().decode('utf-8')

feed = feedparser.parse(content)

print('Feed title:', feed.feed.get('title', ''))
print('Number of entries:', len(feed.entries))
print()

# Calculate 3-day cutoff
now = datetime.now()
cutoff = now - timedelta(days=3)
print(f'Cutoff date (3 days ago): {cutoff.strftime("%Y-%m-%d")}')
print()

# Look at first 5 entries to understand structure
for i, entry in enumerate(feed.entries[:5]):
    print(f'--- Entry {i} ---')
    print('Title:', entry.get('title', ''))
    print('Link:', entry.get('link', ''))
    print('Published:', entry.get('published', entry.get('updated', '')))
    print('Summary (first 300 chars):', str(entry.get('summary', ''))[:300])
    print('Tags:', [t.term for t in entry.get('tags', [])])
    print()