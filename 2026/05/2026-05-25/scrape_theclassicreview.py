import feedparser, json, re
from datetime import datetime, timedelta

cutoff = datetime.now() - timedelta(days=3)
print('Cutoff:', cutoff.strftime('%Y-%m-%d'))

feed = feedparser.parse('https://theclassicreview.com/feed/')
print('Total entries:', len(feed.entries))

items = []
for entry in feed.entries:
    pub = datetime(*entry.published_parsed[:6])
    if pub < cutoff:
        print(f'STOP at {pub.strftime("%Y-%m-%d")}: {entry.title[:60]}')
        break
    
    cats = [c['term'] for c in getattr(entry, 'categories', [])]
    
    summary = getattr(entry, 'summary', '') or ''
    excerpt = re.sub(r'<[^>]+>', '', summary).strip()[:500]
    
    title = entry.title
    parts = title.split(' \u2013 ')
    if len(parts) < 2:
        parts = title.split(' - ')
    
    album = parts[0].replace('Review: ', '').strip() if len(parts) >= 1 else title
    artist = parts[1].strip() if len(parts) >= 2 else ''
    
    print(f'  {pub.strftime("%Y-%m-%d")} | {album[:40]} | {artist[:30]}')
    items.append({
        'album': album,
        'artist': artist,
        'score': None,
        'url': entry.link,
        'source': 'theclassicreview.com',
        'pub_date': pub.strftime('%Y-%m-%d'),
        'tags': [t for t in cats if t is not None],
        'excerpt': excerpt,
        'site_id': 'theclassicreview',
        'crawl_status': 'success',
        'type': 'review'
    })

print(f'\nTotal items in 3-day window: {len(items)}')
with open('/home/liyifan/music-record/2026/05/2026-05-25/the_classic_review_reviews.json', 'w') as f:
    json.dump(items, f, indent=2, ensure_ascii=False)
print('Written to the_classic_review_reviews.json')