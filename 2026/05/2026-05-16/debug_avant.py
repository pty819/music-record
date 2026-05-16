import feedparser, json

d = feedparser.parse('https://avantmusicnews.com/feed/')
for e in d.entries:
    if 'Dusted' in e.get('title',''):
        print("=== Dusted Reviews ===")
        print("Summary type:", type(e.summary))
        print("Summary detail value:", repr(e.get('summary_detail',{}).get('value',''))[:500])
        print("Summary:", repr(e.get('summary',''))[:500])
        break
