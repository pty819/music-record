import feedparser
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
cutoff = now.timestamp() - (3 * 86400)
feed = feedparser.parse("https://icareifyoulisten.com/feed")

print(f"Total items: {len(feed.entries)}")
print(f"Today: {now.strftime('%Y-%m-%d')}")

recent = []
for e in feed.entries:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if pub:
        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
        age_days = (now - pub_dt).total_seconds() / 86400
        if pub_dt.timestamp() >= cutoff:
            recent.append((e, age_days, pub_dt))
            print(f"[{age_days:.1f}d] {e.title[:70]} | {e.get('published','N/A')}")

print(f"\nRecent (3 days): {len(recent)} items")

# Check one entry in detail
if feed.entries:
    e = feed.entries[0]
    print(f"\n--- Sample entry structure ---")
    print(f"title: {e.title}")
    print(f"link: {e.link}")
    print(f"published: {e.get('published')}")
    print(f"author: {e.get('author')}")
    print(f"summary: {str(e.get('summary',''))[:200]}")
    print(f"tags: {[t.term for t in e.get('tags', [])]}")
    print(f"id: {e.get('id')}")