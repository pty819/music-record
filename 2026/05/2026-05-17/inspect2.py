import feedparser, json, re, html
from datetime import datetime, timezone, timedelta

feed = feedparser.parse('https://www.bandwagon.asia/feeds/articles.atom')

# Inspect content of first 3 entries
for i, e in enumerate(feed.entries[:3]):
    print(f"=== Entry {i}: {e.get('title','')[:60]} ===")
    print(f"link: {e.get('link','')}")
    print(f"summary (first 300): {e.get('summary','')[:300]}")
    print(f"summary_detail type: {e.get('summary_detail', {}).get('type','')}")
    content_val = e.get('content', [{}])[0].get('value','') if e.get('content') else ''
    print(f"content (first 300): {content_val[:300]}")
    print()