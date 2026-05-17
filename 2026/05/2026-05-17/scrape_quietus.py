#!/usr/bin/env python3
"""
The Quietus scraper - final version
RSS: https://thequietus.com/columns/quietus-reviews/feed/
"""
import subprocess, re, json
from datetime import datetime, timedelta

RSS_URL = 'https://thequietus.com/columns/quietus-reviews/feed/'
OUTPUT_FILE = '/home/liyifan/music-record/2026/05/2026-05-17/the_quietus_reviews.json'
CUTOFF_DAYS = 3
TAGS = ['experimental', 'electronic', 'jazz', 'world', 'psych', 'prog', 'free-improv']
SITE_ID = 'the_quietus'

def curl(url):
    result = subprocess.run([
        'curl', '-s', '--max-time', '20', '-L', '-A',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        url
    ], capture_output=True, text=True)
    return result.stdout

def parse_date(date_str):
    date_str = date_str.strip()
    for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%d %b %Y']:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            pass
    return None

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_pub_date_from_article(html):
    m = re.search(r'Published\s+\d{1,2}:\d{2}(?:am|pm)?\s+(\d{1,2})\s+(\w+)\s+(\d{4})', html, re.IGNORECASE)
    if m:
        day, month_name, year = m.groups()
        month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                     'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
                     'January': 1, 'February': 2, 'March': 3, 'April': 4, 'June': 6,
                     'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}
        if month_name in month_map:
            return f"{year}-{month_map[month_name]:02d}-{int(day):02d}"
    return None

def parse_review_title(title):
    """
    Parse title into (artist, album, type).
    
    Formats:
    - "Artist – Album" or "Artist - Album" -> artist, album, 'review'
    - "Album of the Week: Artist – Album" -> artist, album, 'review' 
    - "Album of the Week: Some Album Name" (no artist split) -> album, reviewer (from context), 'feature'
    - "Reissue of the Week: The Eighteenth Day Of May" -> band name is the album name; title is album; type=review
    - "Shatterproof: Sam Hoyek's Demonstration 01: Anomalous" -> artist=Shatterproof (band), album="Sam Hoyek's...", type=review
    """
    title = title.replace('&#8217;', "'").replace('&#038;', '&').replace('&#8211;', '–')
    
    # Try standard "Artist – Album" or "Artist - Album"
    m = re.match(r'^(.+?)\s*[-–]\s*(.+)$', title)
    if m:
        return m.group(1).strip(), m.group(2).strip(), 'review'
    
    # Handle "Album of the Week: Artist – Album"
    for prefix in ['Album of the Week: ', 'Reissue of the Week: ', 'Track Review: ', 'Live Album of the Week: ']:
        if title.startswith(prefix):
            rest = title[len(prefix):]
            m = re.match(r'^(.+?)\s*[-–]\s*(.+)$', rest)
            if m:
                return m.group(1).strip(), m.group(2).strip(), 'review'
            # No "Artist – Album" split found inside
            # For reissues/featured items, use title as-is but try to split on colons
            # "Shatterproof: Sam Hoyek's Demonstration..." - first part is the band name
            parts = rest.split(': ', 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip(), 'review'
            return None, rest.strip(), 'review'
    
    return None, title, 'feature'

def extract_score_from_html(html_text):
    patterns = [r'<[^>]+class="[^"]*score[^"]*"[^>]*>(\d+(?:\.\d+)?)</[^>]+>']
    for p in patterns:
        m = re.search(p, html_text, re.IGNORECASE)
        if m:
            score = float(m.group(1))
            if 0 <= score <= 10:
                return score
    return None

# Fetch RSS
rss_text = curl(RSS_URL)
items_xml = re.findall(r'<item>(.*?)</item>', rss_text, re.DOTALL)
print(f"Total RSS items: {len(items_xml)}")

now = datetime.now()
cutoff = now - timedelta(days=CUTOFF_DAYS)
print(f"Cutoff: {cutoff}")

results = []

for item in items_xml:
    title_cdata = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', item)
    title_plain = re.findall(r'<title>(.*?)</title>', item)
    title = (title_cdata or title_plain)[0] if (title_cdata or title_plain) else ''
    title = title.replace('&#8217;', "'").replace('&#038;', '&').replace('&#8211;', '–')
    
    link = re.findall(r'<link>(.*?)</link>', item)
    link = re.sub(r'\?utm_source=rss.*', '', (link[0] if link else ''))
    
    pub_date_str = re.findall(r'<pubDate>(.*?)</pubDate>', item)
    pub_date_parsed = parse_date(pub_date_str[0]) if pub_date_str else None
    
    desc_cdata = re.findall(r'<description><!\[CDATA\[(.*?)\]\]></description>', item, re.DOTALL)
    desc_text = strip_html(desc_cdata[0] if desc_cdata else '')
    
    author_cdata = re.findall(r'<dc:creator><!\[CDATA\[(.*?)\]\]></dc:creator>', item)
    author_plain = re.findall(r'<author>(.*?)</author>', item)
    author_str = (author_cdata or author_plain)[0].strip() if (author_cdata or author_plain) else ''
    
    if pub_date_parsed is None:
        print(f"  SKIP (no date): {title[:60]}")
        continue
    
    pub_dt_naive = pub_date_parsed.replace(tzinfo=None) if pub_date_parsed.tzinfo else pub_date_parsed
    
    if pub_dt_naive < cutoff:
        print(f"  SKIP (too old {pub_dt_naive.strftime('%Y-%m-%d')}): {title[:60]}")
        continue
    
    # Non-music filter
    skip = False
    for kw in ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD ', 'VIDEO ', 'FILM', 'DOCUMENTARY', 'PODCAST', 'TV SHOW', 'SERIES']:
        if kw in title.upper():
            print(f"  SKIP (non-music '{kw}'): {title[:60]}")
            skip = True
            break
    if skip:
        continue
    
    # Parse artist/album
    artist, album, art_type = parse_review_title(title)
    
    # Get pub_date from article page if available (more precise)
    pub_date_str_out = None
    if link:
        article_html = curl(link)
        pub_date_str_out = extract_pub_date_from_article(article_html)
    
    if not pub_date_str_out:
        pub_date_str_out = pub_dt_naive.strftime('%Y-%m-%d')
    
    # Excerpt from description
    excerpt = desc_text[:500]
    if len(desc_text) > 500:
        excerpt = excerpt.rsplit(' ', 1)[0] + '...'
    
    # Final artist: if None (feature), use author/reviewer as artist
    final_artist = artist if artist else author_str
    
    entry = {
        "album": album,
        "artist": final_artist,
        "score": None,
        "url": link,
        "source": "The Quietus",
        "pub_date": pub_date_str_out,
        "tags": TAGS,
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "scraped",
        "type": art_type
    }
    
    print(f"  OK [{art_type}] artist={final_artist} | album={album[:40]} | date={pub_date_str_out}")
    results.append(entry)

print(f"\n=== SUMMARY ===")
print(f"Total: {len(results)} items")
print(f"Reviews: {sum(1 for r in results if r['type']=='review')}")
print(f"Features: {sum(1 for r in results if r['type']=='feature')}")

with open(OUTPUT_FILE, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"Written to {OUTPUT_FILE}")

# Verify
with open(OUTPUT_FILE) as f:
    verify = json.load(f)
print(f"Verified: {len(verify)} items")