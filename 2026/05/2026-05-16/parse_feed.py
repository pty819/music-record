import feedparser
from datetime import datetime, timezone
import json
import re

d = feedparser.parse('https://www.sequenza21.com/feed/')
now = datetime.now(timezone.utc)
three_days_ago = datetime(2026, 5, 13, tzinfo=timezone.utc)  # May 13 = 3 days before May 16

print(f'Total entries: {len(d.entries)}')
print(f'Last build date: {d.feed.get("last_built", "N/A")}')
print()

recent = []
for i, e in enumerate(d.entries[:30]):
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if pub:
        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
        age = (now - pub_dt).days
        print(f'{i}: {pub_dt.strftime("%Y-%m-%d")} ({age}d ago) - {e.title[:80]}')
        if pub_dt >= three_days_ago:
            recent.append((i, e, pub_dt))
    else:
        print(f'{i}: No date - {e.title[:80]}')

print(f'\n--- Within 3-day window ({three_days_ago.date()} to now): {len(recent)} ---')
for i, e, pub_dt in recent:
    print(f'  {pub_dt.strftime("%Y-%m-%d")} - {e.title}')
    print(f'    link: {e.link}')
    summary = getattr(e, 'summary', '') or getattr(e, 'description', '')
    print(f'    summary (first 300): {summary[:300]}')
    content_encoded = getattr(e, 'content', [{}])[0].get('value', '') if hasattr(e, 'content') else ''
    print(f'    has content:encoded: {bool(content_encoded)}')
    print()
