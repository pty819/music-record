import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import json, re
from html import unescape

cutoff = datetime.now(timezone.utc) - timedelta(days=3)

tree = ET.parse('/tmp/wmc_feed.xml')
root = tree.getroot()

def strip_html(text):
    if not text: return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def parse_rfc2822_date(date_str):
    try:
        return parsedate_to_datetime(date_str)
    except:
        return None

def parse_review_info(title, excerpt):
    """
    Parse artist and album from a review title or excerpt.
    Looks for patterns like:
      "Artist – Album (Label, Year)"
      "Artist – Album" (tries to extract from excerpt then)
    Returns (artist, album)
    """
    # Pattern: "Artist – Album (Label, Year)" or similar
    for pattern in [
        r'([A-Za-z\s\.\-\u2019\u2018]+?)\s*[\u2013\u2014]\s*["\u2018]?(.+?)["\u2019]?\s*\([^)]+\d{4}[^)]*\)\s*$',
        r'([A-Za-z\s\.\-\u2019\u2018]+?)\s*[\u2013\u2014]\s*["\u2018]?(.+?)["\u2019]?\s*\(',
    ]:
        m = re.search(pattern, title)
        if m:
            artist = m.group(1).strip()
            album = m.group(2).strip()
            if len(artist) > 2 and len(album) > 2:
                return artist, album

    # Try from excerpt
    m = re.search(r'([A-Za-z\s\.\-\u2019\u2018]+?)\s*[\u2013\u2014]\s*["\u2018]?(.+?)["\u2019]?\s*\(([^)]+\d{4}[^)]*)\)', excerpt)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return None, None

channel = root.find('channel')
items = channel.findall('item') if channel is not None else []
print(f"Found {len(items)} items in XML")

results = []
for item in items:
    pub_date_el = item.find('pubDate')
    if pub_date_el is None:
        continue
    pub_dt = parse_rfc2822_date(pub_date_el.text)
    if pub_dt is None or pub_dt < cutoff:
        continue

    title_el = item.find('title')
    title = unescape(title_el.text) if title_el is not None and title_el.text else ''

    link_el = item.find('link')
    link = link_el.text if link_el is not None else ''

    cats = [unescape(c.text) for c in item.findall('category') if c.text]

    creator_el = item.find('{http://purl.org/dc/elements/1.1/}creator')
    creator = unescape(creator_el.text) if creator_el is not None and creator_el.text else 'World Music Central News Room'

    desc_el = item.find('description')
    desc = unescape(desc_el.text) if desc_el is not None and desc_el.text else ''

    content_el = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
    content = content_el.text if content_el is not None and content_el.text else ''

    raw_text = content or desc
    excerpt = strip_html(raw_text)

    is_album_review = any('album review' in c.lower() for c in cats)

    # Non-music filter
    non_music = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    skip = any(nm in (title + ' ' + excerpt) for nm in non_music)
    if skip:
        print(f"  SKIPPED: {title[:60]}")
        continue

    album = None
    artist = None
    score = None

    if is_album_review:
        artist, album = parse_review_info(title, excerpt)
        if not artist:
            artist = creator
        item_type = "review"
    else:
        album = title
        artist = creator
        item_type = "feature"

    results.append({
        "album": album,
        "artist": artist,
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
    print(f"  [{item_type}] {pub_dt.date()} | artist={artist[:25] if artist else 'N/A'} | album={album[:35] if album else 'N/A'}")
    if is_album_review:
        print(f"           title: {title[:60]}")

print(f"\nTotal: {len(results)}")
with open('/home/liyifan/music-record/2026/05/2026-05-16/world_music_central_reviews.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("Written.")