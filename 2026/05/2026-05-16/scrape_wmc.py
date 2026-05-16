import feedparser
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(days=3)
print("Cutoff:", cutoff)

feed = feedparser.parse("https://worldmusiccentral.org/feed/")
print("Total entries:", len(feed.entries))
recent = []
for e in feed.entries:
    pub = getattr(e, "published_parsed", None)
    if pub:
        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - pub_dt).days
        print(f"  {pub_dt.date()} ({age_days}d ago): {e.title[:70]}")
        if pub_dt >= cutoff:
            recent.append(e)
    else:
        print(f"  No date: {e.title[:70]}")

print(f"\nRecent (within 3 days): {len(recent)}")
for e in recent:
    print(f"  {e.title[:70]}")
    print(f"    link: {e.link}")