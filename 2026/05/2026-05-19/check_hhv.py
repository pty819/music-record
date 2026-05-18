import feedparser
from datetime import datetime, timedelta

# Check RSS
f = feedparser.parse('https://www.hhv-mag.com/rss')
print(f'RSS entries: {len(f.entries)}')
for e in f.entries[:10]:
    print(repr(e.get('title','')), '|', e.get('published',''))
