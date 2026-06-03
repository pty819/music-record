import feedparser
import json
from datetime import datetime, timezone, timedelta

f = feedparser.parse("/home/liyifan/music-record/2026/06/2026-06-04/.scratch/jazztrail.rss")
print(f"feed entries: {len(f.entries)}")
print(f"feed title: {f.feed.get('title')}")
print("---")
cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
recent = []
for e in f.entries:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if not pub:
        continue
    dt = datetime(*pub[:6], tzinfo=timezone.utc)
    if dt >= cutoff:
        recent.append((dt, e))
recent.sort(key=lambda x: x[0], reverse=True)
print(f"within 36h: {len(recent)}")
for dt, e in recent[:5]:
    print(f"  {dt.isoformat()} | {e.get('title')[:60]} | {e.get('link')[:80]}")
