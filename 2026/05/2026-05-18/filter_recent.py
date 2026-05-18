import feedparser
import urllib.request
import ssl
from datetime import datetime, timedelta
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

rss_url = 'https://www.thewire.co.uk/rss'
req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
    content = response.read().decode('utf-8')

feed = feedparser.parse(content)

# Filter entries within 3 days
now = datetime.now()
cutoff = now - timedelta(days=3)
cutoff_str = cutoff.strftime('%Y-%m-%d')

print(f'Looking for entries published after {cutoff_str}')
print(f'Total entries: {len(feed.entries)}')
print()

# Parse dates and filter
recent_entries = []
for entry in feed.entries:
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if pub:
        pub_date = datetime(*pub[:6])
        if pub_date >= cutoff:
            recent_entries.append(entry)

print(f'Recent entries (within 3 days): {len(recent_entries)}')
print()

# Look at categories of recent entries
for i, entry in enumerate(recent_entries[:10]):
    print(f'--- Recent Entry {i} ---')
    print('Title:', entry.get('title', ''))
    print('Link:', entry.get('link', ''))
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if pub:
        pub_date = datetime(*pub[:6])
        print('Date:', pub_date.strftime('%Y-%m-%d'))
    # Check for categories
    categories = []
    for cat in entry.get('categories', []):
        categories.append(cat)
    print('Categories:', categories)
    print('Summary (first 200):', str(entry.get('summary', ''))[:200])
    print()