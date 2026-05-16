import feedparser

d = feedparser.parse('https://avantmusicnews.com/feed/')
for e in d.entries:
    t = e.get('title','')
    if 'Chain D.L.K' in t or 'Free Jazz' in t:
        print(f"=== {t} ===")
        print(repr(e.get('summary',''))[:600])
        print()
