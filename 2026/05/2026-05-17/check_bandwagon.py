import feedparser, json, re
from datetime import datetime, timezone, timedelta

feed = feedparser.parse('https://www.bandwagon.asia/feeds/articles.atom')
cutoff = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=3)
print('Cutoff:', cutoff.isoformat())
print('Total entries:', len(feed.entries))
for e in feed.entries[:20]:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if pub:
        dt = datetime(*pub[:6], tzinfo=timezone(timedelta(hours=8)))
    else:
        dt = None
    in_window = dt >= cutoff if dt else False
    print(in_window, dt, e.get('title','')[:60], e.get('link',''))