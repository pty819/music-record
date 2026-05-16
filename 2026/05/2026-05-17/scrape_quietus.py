#!/usr/bin/env python3
"""
The Quietus scraper - full implementation
RSS: https://thequietus.com/columns/quietus-reviews/feed/
"""
import subprocess, re, json
from datetime import datetime, timedelta

RSS_URL = 'https://thequietus.com/columns/quietus-reviews/feed/'
OUTPUT_FILE = '/home/liyifan/music-record/2026/05/2026-05-17/the_quietus_reviews.json'
CUTOFF_DAYS = 3
TAGS = ['experimental', 'electronic', 'jazz', 'world', 'psych', 'prog', 'free-improv']
SITE_ID = 'the_quietus'

def get_page_via_curl(url):
    result = subprocess.run([
        'curl', '-s', '--max-time', '20', '-L', '-A',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        url
    ], capture_output=True, text=True)
    return result.stdout

def parse_date(date_str):
    """Parse RFC 2822 date like 'Mon, 16 May 2026 00:00:00 +0000'"""
    date_str = date_str.strip()
    for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%d %b %Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            pass
    return None

def strip_html(text):
    """Remove HTML tags from text"""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_score_from_text(text):
    """Look for a score pattern like 8/10, 7.5, etc."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', text)
    if m:
        return float(m.group(1))
    # Look for "X out of 10"
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:out of\s*)?10', text)
    if m:
        return float(m.group(1))
    return None

def parse_review_title(title):
    """Parse 'Artist - Album Name' or similar patterns.
    Returns (artist, album) or (None, title) for features.
    """
    # Common patterns: "Artist – Album Name" or "Artist - Album Name"
    m = re.match(r'^(.+?)\s*[-–]\s*(.+)$', title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    
    # Split on colon first
    if ':' in title:
        parts = title.split(':', 1)
        return parts[0].strip(), parts[1].strip()
    
    return None, title

# Fetch RSS feed
rss_text = get_page_via_curl(RSS_URL)
print(f"RSS response length: {len(rss_text)}")

items_xml = re.findall(r'<item>(.*?)</item>', rss_text, re.DOTALL)
print(f"Total RSS items: {len(items_xml)}")

now = datetime.now()
cutoff = now - timedelta(days=CUTOFF_DAYS)
print(f"Cutoff: {cutoff}")
print(f"Current time: {now}")

# Non-music keywords to filter
NON_MUSIC_KEYWORDS = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD', 'VIDEO', 'FILM', 'DOCUMENTARY', 'PODCAST', 'TV', 'SERIES']

results = []

for item in items_xml:
    # Extract fields
    title_cdata = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', item)
    title_plain = re.findall(r'<title>(.*?)</title>', item)
    title = title_cdata[0] if title_cdata else (title_plain[0] if title_plain else '')
    
    link = re.findall(r'<link>(.*?)</link>', item)
    link = link[0] if link else ''
    link = re.sub(r'\?utm_source=rss.*', '', link)
    
    pub_date_str = re.findall(r'<pubDate>(.*?)</pubDate>', item)
    pub_date_parsed = parse_date(pub_date_str[0]) if pub_date_str else None
    
    # Description in CDATA - this has the full review text per the task spec
    desc_cdata = re.findall(r'<description><!\[CDATA\[(.*?)\]\]></description>', item, re.DOTALL)
    desc_html = desc_cdata[0] if desc_cdata else ''
    desc_text = strip_html(desc_cdata[0] if desc_cdata else '')
    
    # content:encoded has full HTML
    content_cdata = re.findall(r'<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>', item, re.DOTALL)
    content_html = content_cdata[0] if content_cdata else ''
    
    # Get author/reviewer
    author = re.findall(r'<dc:creator><!\[CDATA\[(.*?)\]\]></dc:creator>', item)
    if not author:
        author = re.findall(r'<author>(.*?)</author>', item)
    author = author[0] if author else ''
    
    # Get category
    category = re.findall(r'<category[^>]*><!\[CDATA\[(.*?)\]\]></category>', item)
    category = category[0] if category else ''
    
    # Check pubDate
    pub_dt = pub_date_parsed
    if pub_dt is None:
        print(f"  SKIP (no date): {title[:60]}")
        continue
    
    # Remove timezone for comparison
    if pub_dt.tzinfo is not None:
        pub_dt_naive = pub_dt.replace(tzinfo=None)
    else:
        pub_dt_naive = pub_dt
    
    # Check if within cutoff
    if pub_dt_naive < cutoff:
        print(f"  SKIP (too old {pub_dt_naive.strftime('%Y-%m-%d')}): {title[:60]}")
        continue
    
    print(f"\n  PROCESS: {title[:80]}")
    print(f"    Date: {pub_dt}")
    print(f"    Author: {author}")
    print(f"    Category: {category}")
    
    # Use description as excerpt (strip HTML, first 500 chars)
    excerpt = desc_text[:500] if desc_text else ''
    if len(desc_text) > 500:
        excerpt = excerpt.rsplit(' ', 1)[0] + '...'
    
    # Try to extract artist/album from title
    artist, album = parse_review_title(title)
    
    # Determine if this is a traditional review or feature
    # Check if it's a traditional album review format
    is_feature = False
    if artist is None:
        is_feature = True
    
    # Check for non-music content
    upper_title = title.upper()
    for kw in NON_MUSIC_KEYWORDS:
        if kw in upper_title:
            print(f"    SKIP (non-music keyword '{kw}'): {title[:60]}")
            is_feature = True  # Will be treated as feature, but we'll skip scoring
            break
    
    # If it's a feature type (interview, essay, etc.), set type=feature
    feature_indicators = ['interview', 'essay', 'opinion', 'column', 'feature', 'playlist', 'digest', 'round-up', 'best of', 'top ']
    for indicator in feature_indicators:
        if indicator in title.lower():
            is_feature = True
            break
    
    # Also check if the article URL contains feature-like paths
    if '/feature/' in link or '/interview/' in link or '/opinion/' in link or '/playlist/' in link:
        is_feature = True
    
    # Extract score
    score = None
    if not is_feature:
        # Look for score in description
        score = extract_score_from_text(desc_text)
        if score is None:
            score = extract_score_from_text(content_html)
    
    # Build result
    entry = {
        "album": album if not is_feature else title,
        "artist": artist if not is_feature else (category or ''),
        "score": score,
        "url": link,
        "source": "The Quietus",
        "pub_date": pub_dt.strftime('%Y-%m-%d') if pub_dt else None,
        "tags": TAGS,
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "scraped",
        "type": "feature" if is_feature else "review"
    }
    
    print(f"    Type: {entry['type']}, Score: {score}, Artist: {artist}, Album: {album}")
    print(f"    Excerpt (first 100): {excerpt[:100]}")
    
    results.append(entry)

print(f"\n\n=== SUMMARY ===")
print(f"Total items in 3-day window: {len(results)}")
print(f"Reviews: {sum(1 for r in results if r['type']=='review')}")
print(f"Features: {sum(1 for r in results if r['type']=='feature')}")

# Write output
with open(OUTPUT_FILE, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nWritten to {OUTPUT_FILE}")