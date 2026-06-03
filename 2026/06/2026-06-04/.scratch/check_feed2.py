import feedparser
from datetime import datetime, timezone, timedelta

f = feedparser.parse("/home/liyifan/music-record/2026/06/2026-06-04/.scratch/jazztrail.rss")
print("Most recent entries (by pub date):")
for e in f.entries[:10]:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if pub:
        dt = datetime(*pub[:6], tzinfo=timezone.utc)
    else:
        dt = None
    print(f"  {dt.isoformat() if dt else '???'} | {e.get('title')[:80]}")
print("---")
now = datetime.now(timezone.utc)
print(f"now (UTC): {now.isoformat()}")
print(f"36h ago:   {(now - timedelta(hours=36)).isoformat()}")
