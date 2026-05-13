import feedparser
import json
from datetime import datetime, timedelta

feed = feedparser.parse('/tmp/jj_rss2.xml')
cutoff = datetime.now() - timedelta(days=7)
print(f"Cutoff: {cutoff.date()}, Total items: {len(feed.entries)}")

recent = []
for e in feed.entries:
    if hasattr(e, 'published_parsed') and e.published_parsed:
        dt = datetime(*e.published_parsed[:6])
        age_days = (datetime.now() - dt).days
        if dt >= cutoff:
            recent.append({
                'title': e.get('title', ''),
                'link': e.get('link', ''),
                'pub_date': dt.strftime('%Y-%m-%d'),
                'creator': getattr(e, 'author', 'Jazz Journal'),
                'description': getattr(e, 'summary', '')[:200],
                'age_days': age_days
            })
            print(f"  {dt.date()} ({age_days}d ago): {e.get('title', '')[:60]}")

recent.sort(key=lambda x: x['pub_date'], reverse=True)
print(f"\nRecent items (last 7 days): {len(recent)}")

with open('/tmp/jj_recent.json', 'w') as f:
    json.dump(recent, f)