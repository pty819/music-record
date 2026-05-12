import feedparser
from datetime import datetime, timezone

d = feedparser.parse('prog_mistress_rss.xml')
now = datetime.now(timezone.utc)
print('Total items:', len(d.entries))
print('lastBuildDate:', d.feed.get('lastBuildDate', 'N/A'))
recent = []
for e in d.entries:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if pub:
        dt = datetime(*pub[:6], tzinfo=timezone.utc)
        age = (now - dt).days
        print(f'  [{age}d ago] {e.title[:70]}')
        if age <= 7:
            recent.append(e)
print(f'Recent (7d): {len(recent)}')
for e in recent:
    print(f'  URL: {e.link}')
