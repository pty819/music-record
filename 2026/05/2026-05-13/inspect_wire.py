import urllib.request
import feedparser
import json

RSS_URL = "https://www.thewire.co.uk/audio/rss"
req = urllib.request.Request(RSS_URL, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=15) as resp:
    raw = resp.read().decode('utf-8', errors='replace')

feed = feedparser.parse(raw)

# Print first 5 entries in detail
for i, entry in enumerate(feed.entries[:5]):
    print(f"\n=== Entry {i} ===")
    print(f"Title: {entry.get('title', '')}")
    print(f"Link: {entry.get('link', '')}")
    print(f"Published: {entry.get('published', '')}")
    print(f"Summary: {entry.get('summary', '')[:300]}")
    print(f"Description: {entry.get('description', '')[:300]}")
    if hasattr(entry, 'content'):
        print(f"Content: {entry.content[0].value[:300]}")
    print(f"Keys: {list(entry.keys())}")