import feedparser
from datetime import datetime, timezone
from dateutil import parser as dp

now = datetime.now(timezone.utc)
cutoff = now.timestamp() - 3 * 86400  # 3 days ago

d = feedparser.parse('/tmp/amn_feed.xml')
print(f'Total entries: {len(d.entries)}')
for e in d.entries[:5]:
    print('---')
    print('title:', e.get('title'))
    print('link:', e.get('link'))
    pub = e.get('published') or e.get('updated') or ''
    print('published:', pub)
    if pub:
        try:
            t = dp.parse(pub).astimezone(timezone.utc).timestamp()
            print('ts:', t, 'cutoff:', cutoff, 'in_window:', t >= cutoff)
        except:
            pass
    # Check summary/detail
    print('summary:', (e.get('summary') or '')[:200])
    print('content:', (e.get('content', [{}])[0].get('value', '') or '')[:200] if e.get('content') else '')