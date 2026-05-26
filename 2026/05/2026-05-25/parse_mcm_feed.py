import sys, re, json, html
from datetime import datetime, timedelta

content = sys.stdin.read()
items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
now = datetime.now()
cutoff_days = 3

results = []

for item in items:
    title_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item) or re.search(r'<title>(.*?)</title>', item)
    date_match = re.search(r'<pubDate>(.*?)</pubDate>', item)
    link_match = re.search(r'<link>(.*?)</link>', item)
    desc_cdata = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item)
    desc_plain = re.search(r'<description>(.*?)</description>', item)
    content_encoded = re.search(r'<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>', item, re.DOTALL)

    title = title_match.group(1).strip() if title_match else '?'
    link = link_match.group(1).strip() if link_match else ''
    date_str = date_match.group(1).strip() if date_match else None

    # Get full text from content:encoded or description CDATA
    full_text = ''
    if content_encoded:
        full_text = content_encoded.group(1)
    elif desc_cdata:
        full_text = desc_cdata.group(1)

    # Strip HTML tags
    def strip_html(text):
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = html.unescape(text)
        return text.strip()

    excerpt = strip_html(full_text)[:500] if full_text else ''

    # Parse date
    pub_date = None
    if date_str:
        try:
            d = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S +0000')
            age_days = (now - d).days
            if age_days > cutoff_days:
                continue
            pub_date = d.strftime('%Y-%m-%d')
        except:
            pass

    # Determine type and score
    # If it's a review, we look for a score pattern in the content
    score = None
    article_type = 'review'

    # Check for score patterns like "8/10" or "★★★★"
    score_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:/|／)\s*10', excerpt) or \
                  re.search(r'(?:★|☆)+.*?(\d+(?:\.\d+)?)', excerpt)
    if score_match:
        try:
            score = float(score_match.group(1))
        except:
            pass

    # Check if it mentions review or feature
    lower_text = (full_text + title).lower()
    if any(k in lower_text for k in ['interview', 'conversation', 'in conversation', 'feature']):
        article_type = 'feature'
        score = None

    # Extract album/artist from title
    # Pattern: "Album Name — Artist" or "Artist: Album Name"
    album = ''
    artist = ''
    title_clean = html.unescape(title)

    if '—' in title_clean:
        parts = title_clean.split('—')
        artist = parts[0].strip()
        album = parts[1].strip() if len(parts) > 1 else ''
    elif ':' in title_clean:
        parts = title_clean.split(':')
        artist = parts[0].strip()
        album = parts[1].strip() if len(parts) > 1 else ''
    else:
        album = title_clean

    # Filter: skip non-music items
    skip_patterns = ['(BLU-RAY)', '(UHD)', '(VOD)', '(DVD)']
    if any(p in album or p in artist for p in skip_patterns):
        print(f'SKIPPED (non-music): {title}')
        continue

    entry = {
        'album': album,
        'artist': artist,
        'score': score,
        'url': link,
        'source': 'Modern Classical Music',
        'pub_date': pub_date,
        'tags': [],
        'excerpt': excerpt,
        'site_id': 'modern_classical_music',
        'crawl_status': 'success',
        'type': article_type
    }
    results.append(entry)
    print(f'[{article_type}] {title[:70]} | score={score} | date={pub_date}')

print(f'\nTotal in window: {len(results)}')
print(json.dumps(results, indent=2, ensure_ascii=False))