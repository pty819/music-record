import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_tz, mktime_tz

now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=7)
print(f"Now (UTC): {now}")
print(f"Cutoff: {cutoff}")

feed = feedparser.parse('/tmp/acl_feed.xml')
print(f"Total entries: {len(feed.entries)}")

recent = []
for entry in feed.entries:
    pub_str = entry.get('published') or entry.get('updated') or ''
    if pub_str:
        try:
            parsed = parsedate_tz(pub_str)
            if parsed:
                pub_dt = datetime.fromtimestamp(mktime_tz(parsed), tz=timezone.utc)
                age_days = (now - pub_dt).total_seconds() / 86400
                print(f"  [{age_days:.1f}d] {entry.title[:60]} | {pub_dt.date()} | {entry.link}")
                if pub_dt >= cutoff:
                    recent.append(entry)
        except Exception as ex:
            print(f"  ERROR parsing date: {ex}")

print(f"\nRecent (<=7 days): {len(recent)}")
for e in recent:
    print(f"  {e.title} | {e.link}")
