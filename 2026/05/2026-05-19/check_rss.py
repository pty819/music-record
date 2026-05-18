import feedparser, json
from datetime import datetime, timedelta

# Current date: 2026-05-19, 3-day window: May 16-19
cutoff = datetime(2026, 5, 16)

f = feedparser.parse('https://www.hhv-mag.com/rss')
print(f'RSS status: {f.status}')
print(f'RSS entries: {len(f.entries)}')
for e in f.entries[:15]:
    title = e.get('title','')
    published = e.get('published','')
    link = e.get('link','')
    summary = getattr(e, 'summary', '')[:100] if hasattr(e, 'summary') else ''
    print(f'  {published} | {title[:60]} | {link}')
