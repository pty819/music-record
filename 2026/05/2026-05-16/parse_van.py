import feedparser
from datetime import datetime, timedelta

now = datetime.now()
three_days_ago = now - timedelta(days=3)
print(f"Today: {now}")
print(f"3 days ago: {three_days_ago}")

f = feedparser.parse('/tmp/van_rss.xml')
print('Total entries:', len(f.entries))

recent = []
for e in f.entries:
    try:
        pub = e.get('published_parsed') or e.get('updated_parsed')
        if pub:
            dt = datetime(*pub[:6])
            age_days = (now - dt).days
            print(f"  [{age_days}d] {e.get('title','')[:60]} | {dt.strftime('%Y-%m-%d')}")
            if age_days <= 3:
                recent.append(e)
        else:
            print(f"  [?] no date: {e.get('title','')[:60]}")
    except Exception as ex:
        print(f"  [err] {ex}: {e.get('title','')[:60]}")

print(f"\nIn last 3 days: {len(recent)}")
for e in recent:
    print(f"  - {e.get('title')} | {e.get('link')}")