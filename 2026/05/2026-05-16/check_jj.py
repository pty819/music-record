import feedparser
from datetime import datetime, timezone

feed = feedparser.parse('https://jazzjournal.co.uk/feed/')
today = datetime(2026, 5, 16, tzinfo=timezone.utc)
three_days_ago = datetime(2026, 5, 13, tzinfo=timezone.utc)

for entry in feed.entries:
    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    within = three_days_ago <= pub_date <= today
    cat = entry.get('category', 'N/A')
    print(f"{pub_date.strftime('%Y-%m-%d')} | {within} | {cat} | {entry.title}")
    print(f"  {entry.link}")
