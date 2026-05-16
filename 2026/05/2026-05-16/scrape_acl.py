import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import re
import json

url = 'https://acloserlisten.com/feed/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    content = response.read()

root = ET.fromstring(content)
channel = root.find('channel')
items = channel.findall('item')

now = datetime.utcnow()
three_days_ago = now - timedelta(days=3)
three_days_ago = three_days_ago.replace(tzinfo=None)  # naive for comparison with aware datetimes

results = []

# Non-music filter keywords
NON_MUSIC_KEYWORDS = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD', 'Blu-ray', 'Blu Ray']

def is_non_music(title, artist, album):
    text = f"{title} {artist} {album}".upper()
    for kw in NON_MUSIC_KEYWORDS:
        if kw.upper() in text:
            return True
    return False

def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_full_text(item):
    """Get full text from content:encoded or description, stripping HTML"""
    content_encoded = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
    description = item.find('description')
    
    full_text = ''
    if content_encoded is not None and content_encoded.text:
        full_text = strip_html(content_encoded.text)
    elif description is not None and description.text:
        full_text = strip_html(description.text)
    return full_text

for item in items:
    title = item.find('title').text
    link = item.find('link').text
    pub_date_str = item.find('pubDate').text
    
    try:
        pub_date = parsedate_to_datetime(pub_date_str)
    except:
        pub_date = None
    
    cats = [c.text for c in item.findall('category')]
    creator = item.find('{http://purl.org/dc/elements/1.1/}creator')
    creator_name = creator.text if creator is not None else ''
    
    print(f'---')
    print(f'Title: {title}')
    print(f'Link: {link}')
    print(f'PubDate: {pub_date}')
    print(f'Categories: {cats}')
    print(f'Creator: {creator_name}')
    
    if pub_date and pub_date.replace(tzinfo=None) >= three_days_ago:
        print(f'** WITHIN 3 DAYS **')
        
        # Determine type: review or feature
        # A Closer Listen categories: Featured Articles = feature, others like Experimental, Ambient etc. = review
        is_feature = 'Featured Articles' in cats
        
        # Get full text for excerpt
        full_text = get_full_text(item)
        excerpt = full_text[:500] if full_text else ''
        
        # Try to parse album/artist from content
        # The content usually contains the album name in title: "Artist ~ Album" or "Album ~ Artist"
        # or it mentions the artist/album explicitly
        
        # Parse from title: "Metastasis ~ Dineba" -> artist="Metastasis", album="Dineba"
        album = ''
        artist = ''
        
        if '~' in title:
            parts = title.split('~')
            if len(parts) == 2:
                # Format: "Artist ~ Album" (artist first, album second)
                artist = parts[0].strip()
                album = parts[1].strip()
        
        if not artist and not album:
            # Try to extract from content
            pass
        
        # Filter non-music
        if is_non_music(title, artist, album):
            print(f'** SKIPPED (non-music: video/film) **')
            continue
        
        entry = {
            'album': album,
            'artist': artist,
            'score': None,
            'url': link,
            'source': 'a_closer_listen',
            'pub_date': pub_date.strftime('%Y-%m-%d') if pub_date else '',
            'tags': ', '.join(cats),
            'excerpt': excerpt,
            'site_id': 'a_closer_listen',
            'crawl_status': 'success',
            'type': 'feature' if is_feature else 'review',
        }
        results.append(entry)
        print(f'Type: {entry["type"]}, Album: {album}, Artist: {artist}')
    else:
        print(f'Outside 3 days, skipping')

print(f'\nTotal items within 3 days: {len(results)}')
print(f'Results to save: {len(results)}')

# Write JSON
output_path = '/home/liyifan/music-record/2026/05/2026-05-16/a_closer_listen_reviews.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f'Written to {output_path}')