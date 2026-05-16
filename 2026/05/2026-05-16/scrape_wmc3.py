import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import json
import re
from html import unescape

cutoff = datetime.now(timezone.utc) - timedelta(days=3)
print("Cutoff:", cutoff)

# Parse XML directly since feedparser is failing
tree = ET.parse('/tmp/wmc_feed.xml')
root = tree.getroot()

ns = {
    'rss': 'http://backend.userland.com/rss2',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/',
}

channel = root.find('channel')
items = channel.findall('item') if channel is not None else []
print(f"Found {len(items)} items in XML")

def strip_html(text):
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def parse_rfc2822_date(date_str):
    try:
        return parsedate_to_datetime(date_str)
    except:
        return None

recent_items = []
for item in items:
    pub_date_el = item.find('pubDate')
    if pub_date_el is None:
        continue
    pub_date_str = pub_date_el.text
    pub_dt = parse_rfc2822_date(pub_date_str)
    if pub_dt is None:
        continue

    if pub_dt >= cutoff:
        recent_items.append((pub_dt, item))

print(f"Recent (within 3 days): {len(recent_items)}")

results = []
for pub_dt, item in recent_items:
    title_el = item.find('title')
    title = unescape(title_el.text) if title_el is not None and title_el.text else ''

    link_el = item.find('link')
    link = link_el.text if link_el is not None else ''

    cats = []
    for cat in item.findall('category'):
        if cat.text:
            cats.append(unescape(cat.text))

    creator_el = item.find('dc:creator', ns)
    if creator_el is None:
        creator_ns = '{http://purl.org/dc/elements/1.1/}creator'
        creator_el = item.find(creator_ns)
    creator = unescape(creator_el.text) if creator_el is not None and creator_el.text else ''

    desc_el = item.find('description')
    desc = unescape(desc_el.text) if desc_el is not None and desc_el.text else ''

    content_el = item.find('content:encoded', ns)
    if content_el is None:
        content_ns = '{http://purl.org/rss/1.0/modules/content/}encoded'
        content_el = item.find(content_ns)
    content = content_el.text if content_el is not None and content_el.text else ''

    print(f"\n  {pub_dt.date()}: {title[:70]}")
    print(f"    link: {link}")
    print(f"    categories: {cats}")
    print(f"    creator: {creator}")

    is_album_review = any('album review' in c.lower() for c in cats)

    album = None
    artist = None
    if is_album_review and ' – ' in title:
        parts = title.split(' – ', 1)
        artist = parts[0].strip()
        album = parts[1].strip()
    elif is_album_review and ' by ' in title.lower():
        match = re.search(r'(.+?)\s+by\s+(.+)', title, re.IGNORECASE)
        if match:
            album = match.group(1).strip()
            artist = match.group(2).strip()

    # Use content (full HTML) or description
    raw_text = content or desc
    excerpt = strip_html(raw_text)

    # Extract score
    score = None
    score_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', excerpt)
    if score_match:
        score = float(score_match.group(1))
    else:
        score_match = re.search(r'(\d+(?:\.\d+)?)\s*out of 5', excerpt, re.IGNORECASE)
        if score_match:
            score = float(score_match.group(1)) * 2
        else:
            score_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*5', excerpt)
            if score_match:
                score = float(score_match.group(1)) * 2

    # Non-music filter
    non_music = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    skip = any(nm in (title + ' ' + excerpt) for nm in non_music)
    if skip:
        print(f"    SKIPPED (non-music)")
        continue

    item_type = "review" if is_album_review else "feature"

    results.append({
        "album": album,
        "artist": artist or creator,
        "score": score,
        "url": link,
        "source": "World Music Central",
        "pub_date": pub_dt.strftime("%Y-%m-%d"),
        "tags": cats,
        "excerpt": excerpt,
        "site_id": "world_music_central",
        "crawl_status": "success",
        "type": item_type,
    })

print(f"\n\nTotal items to write: {len(results)}")
print(json.dumps(results, indent=2, ensure_ascii=False)[:3000])