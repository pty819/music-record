import subprocess
import json
import re
from datetime import datetime, timedelta
import sys

# Fetch RSS with cookie
result = subprocess.run([
    'curl', '-s', '-L', '--max-time', '30',
    '-H', 'User-Agent: Mozilla/5.0',
    '-H', 'Cookie: CookieConsent=1',
    'https://www.thewire.co.uk/rss'
], capture_output=True, text=True, timeout=40)

if result.returncode != 0:
    print('RSS fetch failed, trying browser approach')
    sys.exit(1)

content = result.stdout
print(f'RSS content length: {len(content)}')

# Parse with feedparser
try:
    import feedparser
    feed = feedparser.parse(content)
    print(f'Feed title: {feed.feed.get("title", "")}')
    print(f'Number of entries: {len(feed.entries)}')
except ImportError:
    print('feedparser not available')
    sys.exit(1)

# Calculate 3-day cutoff
now = datetime.now()
cutoff = now - timedelta(days=3)
print(f'\nCutoff date (3 days ago): {cutoff.strftime("%Y-%m-%d")}')
print(f'Current date: {now.strftime("%Y-%m-%d")}')

# Parse entries and check dates
all_entries = []
for entry in feed.entries:
    pub_str = entry.get('published', entry.get('updated', ''))
    print(f'\nTitle: {entry.get("title", "")[:60]}')
    print(f'Published string: {pub_str}')
    
    # Try parsing the date
    from email.utils import parsedate_to_datetime
    try:
        pub_date = parsedate_to_datetime(pub_str)
        print(f'Parsed date: {pub_date.strftime("%Y-%m-%d")}')
        in_range = pub_date >= cutoff
        print(f'In range (3 days): {in_range}')
    except Exception as e:
        print(f'Date parse error: {e}')
        in_range = False
    
    print(f'Link: {entry.get("link", "")}')
    print(f'Summary snippet: {str(entry.get("summary", ""))[:200]}')