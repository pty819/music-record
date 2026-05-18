import feedparser, json, re, sys
from datetime import datetime, timedelta
from html.parser import HTMLParser

# ---- config ----
CUTOFF_DAYS = 3
TODAY = datetime(2026, 5, 19)
CUTOFF = TODAY - timedelta(days=CUTOFF_DAYS)
OUTPUT_FILE = '/home/liyifan/music-record/2026/05/2026-05-19/van_magazine_reviews.json'
RSS_URL = 'https://van-magazine.com/feed'
SITE_ID = 'van_magazine'
TAGS = ['classical', 'contemporary classical', 'criticism']

# ---- helpers ----
class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.skip = True
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.skip = False
    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)
    def get_text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.text)).strip()

def strip_html(html):
    if not html:
        return ''
    parser = TextExtractor()
    parser.feed(html)
    return parser.get_text()

def extract_excerpt(entry):
    """Extract excerpt: try summary_detail first, then description, strip HTML, take first 500 chars."""
    text = ''
    # feedparser gives summary_detail with full HTML
    if hasattr(entry, 'summary_detail') and entry.summary_detail and entry.summary_detail.get('value'):
        text = strip_html(entry.summary_detail['value'])
    elif hasattr(entry, 'summary') and entry.summary:
        text = strip_html(entry.summary)
    elif hasattr(entry, 'description') and entry.description:
        text = strip_html(entry.description)
    return text[:500] if text else ''

def parse_date(date_str):
    """Try to parse a date string to YYYY-MM-DD"""
    formats = ['%B %d, %Y', '%b %d, %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None

def is_review_article(entry):
    """Determine if this is a traditional music review based on category tags."""
    # Check if it has category or tag info indicating it's a review
    categories = []
    if hasattr(entry, 'tags'):
        for t in entry.tags:
            categories.append(t.term.lower() if hasattr(t, 'term') else str(t).lower())
    category_str = ' '.join(categories)
    
    # Check for traditional review categories
    review_cats = ['review']
    for cat in review_cats:
        if cat in category_str:
            return True, cat
    return False, categories[0] if categories else 'article'

def determine_type(categories):
    """Determine type: review vs feature based on category."""
    review_cats = ['review']
    for cat in categories:
        if cat.lower() in review_cats:
            return 'review'
    return 'feature'

# ---- main scraping ----
print('=== VAN Magazine Scraper ===')
print(f'Cutoff: {CUTOFF} ({CUTOFF_DAYS} days)')
print()

# Step 1: RSS feed
print(f'Fetching RSS: {RSS_URL}')
d = feedparser.parse(RSS_URL)
print(f'  Status: {d.status if hasattr(d, "status") else "unknown"}')
print(f'  Total entries: {len(d.entries)}')

results = []
seen_urls = set()

for entry in d.entries:
    # Parse date
    pub_str = ''
    if hasattr(entry, 'published') and entry.published:
        pub_str = entry.published
    elif hasattr(entry, 'updated') and entry.updated:
        pub_str = entry.updated
    
    pub_date = None
    if pub_str:
        # Feedparser date parsing
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            tp = entry.published_parsed
            pub_date = datetime(tp[0], tp[1], tp[2])
        elif pub_str:
            pub_date = parse_date(pub_str)
    
    # Check if within range
    if pub_date and isinstance(pub_date, datetime):
        in_range = pub_date >= CUTOFF
    else:
        in_range = False
    
    print(f'  Entry: {entry.title[:60]}')
    print(f'    Date str: {pub_str}')
    print(f'    Parsed: {pub_date}')
    print(f'    In range: {in_range}')
    
    if not in_range:
        print(f'    -> SKIP (outside 3-day window)')
        continue
    
    # Get URL
    url = entry.get('link', '')
    if not url or url in seen_urls:
        continue
    seen_urls.add(url)
    
    # Get categories
    categories = []
    if hasattr(entry, 'tags'):
        for t in entry.tags:
            categories.append(t.term if hasattr(t, 'term') else str(t))
    
    # Determine type
    doc_type = determine_type(categories)
    
    # For traditional reviews, we need album/artist/score
    # For features, title -> album, category -> artist, score = null
    title = entry.title
    
    if doc_type == 'review':
        # Try to extract album/artist from title or description
        # Title format often: "Album Name" by Artist or Artist: Album Name
        album = ''
        artist = ''
        score = None
        
        # Try to parse title for "X" by "Y" pattern
        desc = strip_html(entry.get('description', '')[:1000])
        
        # For reviews: look for quoted titles and "by" patterns
        # e.g. 'Gabrielle Goliath's "Elegy" at the Venice Biennale'
        # We may not have structured data - so put what we can
        album = title
        artist = desc.split('by')[-1].strip() if 'by' in desc else ''
        # Remove artist from album if it was prepended
    else:
        album = title
        artist = ', '.join(categories) if categories else ''
        score = None
    
    # Get excerpt
    excerpt = extract_excerpt(entry)
    
    item = {
        'album': album,
        'artist': artist,
        'score': score,
        'url': url,
        'source': 'van_magazine',
        'pub_date': pub_date.strftime('%Y-%m-%d') if isinstance(pub_date, datetime) else str(pub_date),
        'tags': TAGS,
        'excerpt': excerpt,
        'site_id': SITE_ID,
        'crawl_status': 'success',
        'type': doc_type
    }
    results.append(item)
    print(f'    -> INCLUDE as {doc_type}')

print()
print(f'Total items to save: {len(results)}')

# Save output
with open(OUTPUT_FILE, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f'Written to: {OUTPUT_FILE}')

# Summary
if results:
    print()
    print('Items:')
    for r in results:
        print(f"  [{r['type']}] {r['album']} | {r['artist']} | score={r['score']} | {r['pub_date']}")
else:
    print('No items in 3-day window. Output empty array.')
