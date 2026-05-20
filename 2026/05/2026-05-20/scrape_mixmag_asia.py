#!/usr/bin/env python3
import subprocess, re
from datetime import datetime, timedelta

# Fetch RSS
result = subprocess.run(
    ['curl', '-s', '--max-time', '20',
     'https://mixmag.asia/rss.xml',
     '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'],
    capture_output=True, text=True
)
content = result.stdout

# Extract items
items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
print(f'Total items in RSS: {len(items)}')

three_days_ago = datetime.utcnow() - timedelta(days=3)
print(f'Cutoff date: {three_days_ago.strftime("%Y-%m-%d")}')

review_keywords = ['review', 'album', 'track', 'ep', 'single', 'premiere', 'rating', '★★★★', '★★★', '★★', '★']
recent_reviews = []

for item in items:
    title_m = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
    link_m = re.search(r'<link>(.*?)</link>', item, re.DOTALL)
    pub_m = re.search(r'<pubDate>(.*?)</pubDate>', item, re.DOTALL)
    desc_m = re.search(r'<description>(.*?)</description>', item, re.DOTALL)
    
    title_text = title_m.group(1).strip() if title_m else ''
    link_text = link_m.group(1).strip() if link_m else ''
    pub_text = pub_m.group(1).strip() if pub_m else ''
    desc_text = desc_m.group(1).strip() if desc_m else ''
    
    try:
        pub_date = datetime.strptime(pub_text, '%a, %d %b %Y %H:%M:%S %z')
    except:
        pub_date = None
    
    is_review = any(kw in title_text.lower() or kw in desc_text.lower() for kw in review_keywords)
    in_range = pub_date and pub_date.replace(tzinfo=None) >= three_days_ago.replace(tzinfo=None)
    
    marker = 'REVIEW' if is_review else '----'
    range_marker = 'IN RANGE' if in_range else 'OLD'
    date_str = pub_date.strftime('%Y-%m-%d') if pub_date else 'NO DATE'
    print(f'  [{date_str}] {marker} {range_marker}: {title_text[:80]}')
    
    if is_review and in_range:
        recent_reviews.append({
            'title': title_text,
            'link': link_text,
            'pub': pub_text,
            'desc': desc_text
        })

print(f'\nRecent review items: {len(recent_reviews)}')
for r in recent_reviews:
    print(f'  - {r["title"]}')
    print(f'    {r["link"]}')
    print(f'    {r["pub"]}')
