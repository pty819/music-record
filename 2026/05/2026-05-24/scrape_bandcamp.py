import feedparser, json, re, html
from datetime import datetime, timedelta
import urllib.request

cutoff = datetime.utcnow() - timedelta(days=3)

feed = feedparser.parse('https://daily.bandcamp.com/feed')

items = []
for e in feed.entries:
    pub_parsed = e.get('published_parsed') or e.get('dc_date')
    if not pub_parsed:
        continue
    pub_dt = datetime(*pub_parsed[:6])
    if pub_dt >= cutoff:
        items.append(e)

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_content(url):
    """Fetch page and extract text content"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8', errors='replace')
        return content
    except Exception as ex:
        return ''

results = []
SKIP_PATTERNS = ['BLU-RAY', 'UHD', 'VOD', 'DVD']
SITE = 'bandcamp_daily'

for e in items:
    cat = e.get('category', '')
    link = e.link
    title = e.title

    # Non-music filter
    skip = any(p in title for p in SKIP_PATTERNS)
    if skip:
        print(f'SKIP (non-music): {title}')
        continue

    # Determine type
    if cat == 'Album of the Day':
        item_type = 'review'
    elif cat == 'Features':
        item_type = 'feature'
    else:
        item_type = 'review'

    # Get full page for better excerpt + score
    content = get_content(link)
    excerpt = ''
    score = None

    if content:
        # Extract text from page (simple approach)
        # Try to find review body text
        body_match = re.search(r'<p[^>]*>(.{200,}?)</p>', content)
        if body_match:
            excerpt = strip_html(body_match.group(1))[:500]

    # Fallback to RSS summary
    if not excerpt:
        raw_summary = e.get('summary', '')
        excerpt = strip_html(raw_summary)[:500]

    pub_parsed = e.get('published_parsed', e.get('dc_date'))
    pub_dt = datetime(*pub_parsed[:6]) if pub_parsed else datetime.utcnow()
    pub_date = pub_dt.strftime('%Y-%m-%d')

    # Try to extract album/artist from title
    # Title patterns: "Album Artist, "Title"" or "Artist, "Title""
    album = ''
    artist = ''
    title_clean = title.strip('"').strip()

    # Extract "Artist, "Title"" pattern
    m = re.match(r'^(.+?),\s+["""](.+)["""]\s*$', title_clean)
    if m:
        artist = m.group(1).strip()
        album = m.group(2).strip()
    else:
        # Fallback: title is just the album or a descriptive name
        album = title_clean

    results.append({
        'album': album,
        'artist': artist,
        'score': score,
        'url': link,
        'source': 'Bandcamp Daily',
        'pub_date': pub_date,
        'tags': [cat] if cat else [],
        'excerpt': excerpt,
        'site_id': SITE,
        'crawl_status': 'success',
        'type': item_type,
    })
    print(f'ADDED: [{item_type}] {artist} - {album} ({pub_date})')

print(f'\nTotal: {len(results)} items')
with open('bandcamp_daily_reviews.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print('Written to bandcamp_daily_reviews.json')