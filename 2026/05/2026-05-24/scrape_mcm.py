import feedparser
from datetime import datetime, timezone, timedelta
import json, re

cutoff = datetime.now(timezone.utc) - timedelta(days=3)
feed = feedparser.parse('https://www.modernclassicalmusic.com/feed/')
print('Total entries:', len(feed.entries))

results = []
for e in feed.entries:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    dt = datetime(*pub[:6], tzinfo=timezone.utc) if pub else None
    if dt and dt < cutoff:
        print('SKIP (old):', e.title[:60])
        continue
    cats = [c['term'] for c in e.get('tags', [])]
    title_lower = e.title.lower()
    if any(x in title_lower for x in ['blu-ray','uhd','vod','dvd']):
        print('SKIP (format):', e.title)
        continue
    html = e.get('content',[{}])[0].get('value','') or e.get('summary','')
    excerpt = re.sub(r'<[^>]+>', ' ', html)
    excerpt = re.sub(r'\s+', ' ', excerpt).strip()[:500]
    # Extract album/artist from title: "Title – Album Name" or "Album - Artist" pattern
    title = e.title
    album = None
    artist = None
    if ' – ' in title:
        parts = title.split(' – ')
        if len(parts) == 2:
            album = parts[1].strip()
    # Also try to extract artist from content
    content_text = re.sub(r'<[^>]+>', ' ', html)
    artist_match = re.search(r'(?:by|from|composer|artist)[\s:]+([A-Z][a-zA-Z\s]+)', content_text, re.IGNORECASE)
    
    item = {
        'album': album, 'artist': artist, 'score': None,
        'url': e.link, 'source': 'Modern Classical Music',
        'pub_date': dt.isoformat() if dt else None,
        'tags': cats, 'excerpt': excerpt,
        'site_id': 'modern_classical_music',
        'crawl_status': 'success',
        'type': 'review' if 'Review' in cats else 'feature'
    }
    results.append(item)
    print('ADDED:', e.title[:70], '|', dt.date() if dt else None)

print()
print('Count:', len(results))
with open('modern_classical_music_reviews.json','w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print('Written.')