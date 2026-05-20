import feedparser
from datetime import datetime, timedelta

feed_url = "https://igloomag.com/feed"
print(f"Trying RSS: {feed_url}")
try:
    feed = feedparser.parse(feed_url)
    title = feed.feed.get("title", "N/A")
    print(f"Feed title: {title}")
    print(f"Entries count: {len(feed.entries)}")
    
    cutoff = datetime.now() - timedelta(days=3)
    recent = []
    for e in feed.entries:
        pub = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        if pub:
            pub_dt = datetime(*pub[:6])
            if pub_dt >= cutoff:
                recent.append({
                    "title": e.get("title", ""),
                    "link": e.get("link", ""),
                    "published": getattr(e, "published", ""),
                    "summary": getattr(e, "summary", "")[:200],
                })
    print(f"Recent entries (3 days): {len(recent)}")
    for r in recent:
        print(f"  - {r['title']} | {r['published']}")
except Exception as ex:
    print(f"RSS failed: {ex}")
