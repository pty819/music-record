import feedparser
import json
import re
import subprocess
from datetime import datetime, timedelta
from html import unescape

# Read RSS
feed = feedparser.parse('/tmp/jj_rss2.xml')
cutoff = datetime.now() - timedelta(days=7)

recent_items = []
for e in feed.entries:
    if hasattr(e, 'published_parsed') and e.published_parsed:
        dt = datetime(*e.published_parsed[:6])
        if dt >= cutoff:
            recent_items.append({
                'title': e.get('title', ''),
                'link': e.get('link', ''),
                'pub_date': dt.strftime('%Y-%m-%d'),
                'creator': getattr(e, 'author', 'Jazz Journal'),
                'description': getattr(e, 'summary', ''),
                'tags': ['jazz', 'reviews']
            })

print(f"Processing {len(recent_items)} RSS items")

reviews = []

def fetch_page(url):
    """Fetch page with curl, return html or None if blocked"""
    slug = url.rstrip('/').split('/')[-1]
    cache_file = f'/tmp/jj_page_{slug}.html'
    
    result = subprocess.run(
        ['curl', '-s', '--max-time', '10', '-L', '-A',
         'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
         url, '-o', cache_file],
        capture_output=True, text=True, timeout=15
    )
    
    import os
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 500:
        with open(cache_file, 'r', errors='ignore') as f:
            html = f.read()
        if 'cloudflare' not in html.lower() and 'checking your browser' not in html.lower():
            return html
    return None

def extract_reviews_from_text(text, source_url, pub_date, tags):
    """Extract review entries from Jazz Journal page text.
    Format: Artist: Album Title They say : Description
    """
    results = []
    
    # Find all positions of 'They say'
    for m in re.finditer(r'They say', text):
        pos = m.start()
        before = text[max(0, pos-250):pos]
        
        # Look for the Artist: Album pattern before 'They say'
        colon_pattern = r'([A-Za-z][A-Za-z\s\-\'\,\.]+?)\s*:\s*([^\n\r]+?)(?:\s+They\s+say|$)'
        matches = list(re.finditer(colon_pattern, before))
        
        if matches:
            # Take the last match
            last = matches[-1]
            artist = last.group(1).strip()
            album = last.group(2).strip().rstrip('.')
            
            # Skip garbage
            skip = False
            skip_words = ['advertisement', 'editor\'s pick', 'facebook', 'tdi_', '.td-', 
                         'news', 'reviews', 'audio', 'book', 'film', 'live', 'request']
            for sw in skip_words:
                if sw in artist.lower():
                    skip = True
                    break
            
            if len(artist) < 3 or len(album) < 3:
                skip = True
            
            if skip:
                continue
            
            # Clean up common issues
            # If artist looks like partial (single word that could be first name of longer name)
            # but we have reasonable data, keep it
            artist = re.sub(r'^\s+', '', artist)
            artist = re.sub(r'\s+$', '', artist)
            
            # Try to find score
            after = text[pos:pos+300]
            score = None
            score_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', after)
            if score_match:
                score = float(score_match.group(1))
            
            # Extract description
            desc_match = re.search(r'They\s+say\s*:\s*(.{20,250})', after)
            desc = desc_match.group(1).strip() if desc_match else ''
            
            # Clean description - remove label info at start if present
            desc = re.sub(r'^\([^\)]+\)\s*[-–]\s*', '', desc)
            desc = re.sub(r'^[\w\s]+:\s*', '', desc)  # Remove leading "Artist:" pattern
            
            results.append({
                'album': album,
                'artist': artist,
                'score': score,
                'url': source_url,
                'source': 'Jazz Journal',
                'pub_date': pub_date,
                'tags': tags,
                'excerpt': desc[:300] if desc else '',
                'site_id': 'jazz_journal',
                'crawl_status': 'listing'
            })
    
    return results

for item in recent_items:
    url = item['link']
    print(f"\nProcessing: {item['title'][:60]}")
    
    html = fetch_page(url)
    
    if html:
        # Clean HTML
        clean = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL)
        clean = re.sub(r'<style[^>]*>.*?</style>', ' ', clean, flags=re.DOTALL)
        clean = re.sub(r'<[^>]+>', ' ', clean)
        clean = unescape(clean)
        clean = re.sub(r'\s+', ' ', clean)
        
        # Extract reviews
        extracted = extract_reviews_from_text(clean, url, item['pub_date'], item['tags'])
        
        if extracted:
            print(f"  Extracted {len(extracted)} reviews")
            reviews.extend(extracted)
        else:
            print(f"  No sub-reviews found, storing as article entry")
            reviews.append({
                'album': item['title'],
                'artist': item['creator'],
                'score': None,
                'url': url,
                'source': 'Jazz Journal',
                'pub_date': item['pub_date'],
                'tags': item['tags'],
                'excerpt': clean[:300],
                'site_id': 'jazz_journal',
                'crawl_status': 'listing'
            })
    else:
        print(f"  Page blocked/fetch failed, using RSS description")
        desc = re.sub(r'<[^>]+>', ' ', item['description'])
        desc = unescape(desc)
        desc = re.sub(r'\s+', ' ', desc).strip()
        reviews.append({
            'album': item['title'],
            'artist': item['creator'],
            'score': None,
            'url': url,
            'source': 'Jazz Journal',
            'pub_date': item['pub_date'],
            'tags': item['tags'],
            'excerpt': desc[:500] if desc else item['title'],
            'site_id': 'jazz_journal',
            'crawl_status': 'rss_listing'
        })

print(f"\nTotal reviews: {len(reviews)}")

# Write output
output = {
    'site': 'jazz_journal',
    'count': len(reviews),
    'crawl_status': 'success' if reviews else 'no_recent_content',
    'method': 'RSS feed + curl (cloudflare fallback)',
    'days_scanned': '7',
    'reviews': reviews
}

with open('/home/liyifan/music-record/2026/05/2026-05-13/jazz_journal_reviews.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"\nWritten to jazz_journal_reviews.json")
for r in reviews:
    print(f"  {r['pub_date']} | {r['album'][:45]} | {r['artist'][:25]} | score={r['score']}")