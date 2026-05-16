#!/usr/bin/env python3
"""
Scrape scores from The Quietus review pages - improved.
"""
import subprocess, re, json
from datetime import datetime, timedelta

OUTPUT_FILE = '/home/liyifan/music-record/2026/05/2026-05-17/the_quietus_reviews.json'

def fetch_page_text(url):
    result = subprocess.run([
        'curl', '-s', '--max-time', '20', '-L', '-A',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        url
    ], capture_output=True, text=True)
    return result.stdout

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_score_from_html(html_text):
    """Look for score patterns in review body."""
    # Quietus may not always show scores, look for common patterns
    patterns = [
        r'<[^>]+class="[^"]*score[^"]*"[^>]*>(\d+(?:\.\d+)?)</[^>]+>',
        r'(\d+(?:\.\d+)?)\s*/\s*10',
        r'(\d+(?:\.\d+)?)\s+out\s+of\s+10',
    ]
    for p in patterns:
        m = re.search(p, html_text, re.IGNORECASE)
        if m:
            score = float(m.group(1))
            if 0 <= score <= 10:
                return score
    return None

def find_article_body(html_text):
    """Extract the main article content area."""
    # Try common article containers
    for pattern in [
        r'<article[^>]*>(.*?)</article>',
        r'<div[^>]+class="[^"]*article[^"]*"[^>]*>(.*?)</div>',
        r'<main[^>]*>(.*?)</main>',
        r'<div[^>]+class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
    ]:
        m = re.search(pattern, html_text, re.DOTALL)
        if m and len(m.group(1)) > 500:
            return m.group(1)
    return None

def parse_review_title_to_artist_album(title):
    """Parse review title into artist and album.
    Titles like:
    - "Reissue of the Week: The Eighteenth Day Of May" -> artist=None (feature-like), album=title
    - "Speedy J – Walkman" -> artist="Speedy J", album="Walkman"
    - "Darkthrone – Pre-Historic Metal" -> artist="Darkthrone", album="Pre-Historic Metal"
    - "Album of the Week: Shatterproof: Sam Hoyek's Demonstration 01: Anomalous" -> artist="Shatterproof", album="Sam Hoyek's..."
    
    For "Artist – Album" (en dash) or "Artist - Album" (hyphen):
    - If the part before dash is the same as category name (Reissue of the Week, Album of the Week), treat as feature
    """
    CATEGORIES = ['Reissue of the Week', 'Album of the Week', 'Track Review', 'Live Album of the Week']
    
    for cat in CATEGORIES:
        if title.startswith(cat + ': '):
            # This is a categorized review - the actual album is after the colon
            rest = title[len(cat)+2:]
            # Try to split on dash
            m = re.match(r'^(.+?)\s*[-–]\s*(.+)$', rest)
            if m:
                return m.group(1).strip(), m.group(2).strip(), 'review'
            else:
                # The whole rest is the album name
                return None, rest.strip(), 'review'
    
    # Standard "Artist – Album" or "Artist - Album" format
    m = re.match(r'^(.+?)\s*[-–]\s*(.+)$', title)
    if m:
        return m.group(1).strip(), m.group(2).strip(), 'review'
    
    # No recognizable pattern -> feature
    return None, title, 'feature'

# Load existing results
with open(OUTPUT_FILE) as f:
    results = json.load(f)
print(f"Loaded {len(results)} items")

for item in results:
    url = item['url']
    title_raw = item['album']  # This is currently the title from RSS
    
    html = fetch_page_text(url)
    
    # Extract article body for better excerpt
    body = find_article_body(html)
    if body:
        body_text = strip_html(body)
        excerpt = body_text[:500]
        if len(body_text) > 500:
            excerpt = excerpt.rsplit(' ', 1)[0] + '...'
        item['excerpt'] = excerpt
    
    # Extract score if present
    score = extract_score_from_html(html)
    if score is not None:
        item['score'] = score
    
    # Try to extract author from page
    author_match = re.search(r'class="author[^"]*"[^>]*>([^<]+)<', html)
    if author_match:
        item['reviewer'] = author_match.group(1).strip()
    
    # Look for pubDate / date published
    date_match = re.search(r'<time[^>]+datetime="([^"]+)"', html)
    if date_match:
        item['pub_date'] = date_match.group(1)[:10]  # YYYY-MM-DD
    
    print(f"Processed: {item['artist']} - {item['album']} | score={item['score']} | type={item['type']}")

# Save updated results
with open(OUTPUT_FILE, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nWritten to {OUTPUT_FILE}")

# Verify file
with open(OUTPUT_FILE) as f:
    final = json.load(f)
print(f"Final item count: {len(final)}")
for r in final:
    print(f"  [{r['type']}] {r['artist']} - {r['album']} | score={r['score']} | date={r['pub_date']}")
    print(f"    url: {r['url']}")
    print(f"    excerpt: {r['excerpt'][:100]}...")