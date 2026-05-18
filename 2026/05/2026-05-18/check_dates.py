import feedparser
from datetime import datetime, timezone

# Today: the task was spawned on 2026-05-18 (local), but datetime.utcnow() vs timezone.utc matters
# Local time: May 18 04:20 AM CST = May 17 20:20 UTC
# We'll use the timezone-aware now to be precise

now_utc = datetime.now(timezone.utc)
print(f"UTC now: {now_utc}")

# Cutoff: 3 days ago
cutoff = now_utc.timestamp() - (3 * 86400)
cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
print(f"Cutoff (3 days ago): {cutoff_dt}")

feed = feedparser.parse("https://icareifyoulisten.com/feed")
print(f"Total items: {len(feed.entries)}")
print()

recent_items = []
for e in feed.entries:
    pub = e.get('published_parsed')
    if pub:
        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
        age_days = (now_utc - pub_dt).total_seconds() / 86400
        in_window = pub_dt.timestamp() >= cutoff
        print(f"[age={age_days:.1f}d, in_window={in_window}] {e.title[:60]}")
        print(f"   pubDate: {e.get('published')}  |  utc ts: {pub_dt.timestamp()}")
        if in_window:
            recent_items.append(e)

print(f"\nRecent items (within 3 days): {len(recent_items)}")

# Also check: if we use local date of 2026-05-18 as "today"
from datetime import datetime as dt
local_now = dt(2026, 5, 18, 4, 20, tzinfo=timezone.utc)
print(f"\nWith local 'today' of 2026-05-18 04:20 UTC:")
cutoff2 = local_now.timestamp() - (3 * 86400)
for e in feed.entries:
    pub = e.get('published_parsed')
    if pub:
        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
        age_days = (local_now - pub_dt).total_seconds() / 86400
        in_window = pub_dt.timestamp() >= cutoff2
        if in_window:
            print(f"  [age={age_days:.1f}d] {e.title[:60]}")