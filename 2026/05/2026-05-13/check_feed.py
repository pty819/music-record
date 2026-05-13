import feedparser
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=7)
print('Cutoff:', cutoff.isoformat())

feed = feedparser.parse('https://newmusicbuff.com/feed/')
print('Total items in feed:', len(feed.entries))
for i, e in enumerate(feed.entries):
    pub = getattr(e, 'published_parsed', None)
    if pub:
        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
    else:
        pub_dt = None
    age = (now - pub_dt).days if pub_dt else '?'
    in_range = pub_dt >= cutoff if pub_dt else False
    print(f'[{i}] {e.get("title","")[:70]} | {pub_dt} ({age}d) | in_range={in_range}')
    if i < 5:
        print('   URL:', e.get('link', ''))
        print('   Tags:', [t.term for t in getattr(e, 'tags', [])])
