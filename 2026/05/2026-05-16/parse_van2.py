import feedparser

f = feedparser.parse('/tmp/van_rss.xml')
for e in f.entries:
    title = e.get('title', '')
    link = e.get('link', '')
    cats = [c.get('term', '') for c in e.get('tags', [])]
    print(f"TITLE: {title}")
    print(f"LINK: {link}")
    print(f"TAGS: {cats}")
    print(f"SUMMARY: {str(e.get('summary',''))[:300]}")
    print("---")