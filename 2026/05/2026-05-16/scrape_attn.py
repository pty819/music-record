import feedparser
from datetime import datetime, timezone
import re
import json

# Parse the RSS feed
feed = feedparser.parse("https://www.attnmagazine.co.uk/rss/")

print(f"Title: {feed.feed.title}")
print(f"Last build date: {feed.feed.get('last_built_date', feed.feed.get('published', 'N/A'))}")
print(f"Number of items: {len(feed.entries)}")
print()

# Current date for comparison
now = datetime(2026, 5, 16, tzinfo=timezone.utc)
three_days_ago = datetime(2026, 5, 13, tzinfo=timezone.utc)

print(f"Current date: {now}")
print(f"3 days ago: {three_days_ago}")
print()

# Check each item
for i, entry in enumerate(feed.entries):
    pub_date_str = entry.get('published') or entry.get('updated', 'N/A')
    print(f"Item {i}: {entry.title[:60]}")
    print(f"  pubDate: {pub_date_str}")
    print(f"  link: {entry.link}")
    # Try to parse the date
    if pub_date_str != 'N/A':
        try:
            pub_date = feedparser._parse_date(pub_date_str)
            if pub_date:
                pub_dt = datetime(*pub_date[:6], tzinfo=timezone.utc)
                in_window = pub_dt >= three_days_ago
                print(f"  parsed: {pub_dt}, in_window={in_window}")
        except Exception as e:
            print(f"  date parse error: {e}")
    print()
