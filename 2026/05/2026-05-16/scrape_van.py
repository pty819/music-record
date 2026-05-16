import feedparser
import json
import re
from datetime import datetime

f = feedparser.parse('/tmp/van_rss.xml')

now = datetime.now()
three_days_ago = now - __import__('datetime').timedelta(days=3)

items = []
for e in f.entries:
    # Parse date
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if not pub:
        continue
    dt = datetime(*pub[:6])
    age_days = (now - dt).days
    if age_days > 3:
        continue

    title = e.get('title', '')
    link = e.get('link', '')
    summary_raw = str(e.get('summary', ''))
    # Strip HTML tags
    summary_clean = re.sub(r'<[^>]+>', '', summary_raw).strip()
    excerpt = summary_clean[:500] if summary_clean else ''

    # Get category tags
    cats = [c.get('term', '') for c in e.get('tags', [])]
    site_tags = [t for t in cats if t != 'New in VAN']

    # Determine type
    is_review = 'Review' in cats
    the_type = 'review' if is_review else 'feature'

    # Non-music filter: check for DVD/BLU-RAY/UHD/VOD
    skip_keywords = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    combined = title + ' ' + ' '.join(cats)
    if any(kw in combined for kw in skip_keywords):
        print(f"SKIP (non-music): {title}")
        continue

    # Extract author from RSS if available (sometimes in author field)
    author = e.get('author', '')

    item = {
        'album': title,
        'artist': author if author else '',
        'score': None,
        'url': link,
        'source': 'van-magazine.com',
        'pub_date': dt.strftime('%Y-%m-%d'),
        'tags': site_tags if site_tags else ['classical', 'contemporary classical', 'criticism'],
        'excerpt': excerpt,
        'site_id': 'van_magazine',
        'crawl_status': 'paywall',
        'type': the_type
    }
    items.append(item)
    print(f"ADDED [{the_type}] {title}")

print(f"\nTotal items: {len(items)}")
with open('van_magazine_reviews.json', 'w') as fp:
    json.dump(items, fp, indent=2)
print("Written to van_magazine_reviews.json")