import feedparser
import ssl
import json
import sys
import re
from datetime import datetime, timezone

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

import urllib.request
url = 'https://www.sequenza21.com/feed/'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
    data = resp.read()

d = feedparser.parse(data)

# 3-day window
now = datetime.now(timezone.utc)
cutoff = datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)  # 3 days before May 18

print(f'Total entries: {len(d.entries)}', file=sys.stderr)
recent = []
for e in d.entries:
    pub = e.get('published') or e.get('updated') or ''
    try:
        # feedparser date parsing
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub)
    except:
        continue
    if dt >= cutoff:
        recent.append(e)

print(f'Recent entries (>= May 15): {len(recent)}', file=sys.stderr)

def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"').replace('&#8211;', '–').replace('&#8212;', '—')
    return text.strip()

def is_music_review(entry):
    """Return True if this looks like a music review (not DVD/Blu-ray/etc.)"""
    title = entry.get('title', '') + ' ' + (entry.get('summary', '') or '')
    non_music = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    for kw in non_music:
        if kw.lower() in title.lower():
            return False
    return True

def guess_type(entry):
    """Guess whether this is a review or feature"""
    title = entry.get('title', '')
    summary = entry.get('summary', '') or ''
    combined = title + ' ' + summary
    # Features/articles often contain these patterns
    feature_kw = ['interview', 'profile', 'festival', 'concert', 'premiere', 'preview', 'column', 'essay']
    for kw in feature_kw:
        if kw.lower() in combined.lower():
            return 'feature'
    return 'review'

import re

items = []
for e in recent:
    if not is_music_review(e):
        continue
    title = strip_html(e.get('title', ''))
    summary = e.get('summary', '') or e.get('subtitle', '') or ''
    excerpt = strip_html(summary)[:500]

    # Try to parse artist/album from title or summary
    # Common patterns: "Artist: Album" or "Album (Artist)" or "Artist @ Event"
    artist = ''
    album = ''
    link = e.get('link', '')

    # Try to extract from summary which may have more detail
    summary_text = strip_html(summary)

    # Look for common patterns
    # Pattern: "Album Title (Artist)" or "Artist – Album"
    match = re.search(r'^(.+?)\s+[–—-]\s+(.+?)$', title)
    if match:
        artist = match.group(1).strip()
        album = match.group(2).strip()
    else:
        # Try parens
        match = re.search(r'^(.+?)\s+\((.+?)\)', title)
        if match:
            album = match.group(1).strip()
            artist = match.group(2).strip()
        else:
            # Use title as album, empty artist
            album = title

    try:
        from email.utils import parsedate_to_datetime
        pub_dt = parsedate_to_datetime(e.get('published') or e.get('updated', ''))
        pub_date = pub_dt.strftime('%Y-%m-%d')
    except:
        pub_date = ''

    item_type = guess_type(e)

    # Try to find a score in the content
    score = None
    score_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:stars?|/|out of|over|on)\s*(\d+)', summary, re.I)
    if score_match:
        try:
            score = float(score_match.group(1))
        except:
            pass

    items.append({
        'album': album,
        'artist': artist,
        'score': score,
        'url': link,
        'source': 'Sequenza21',
        'pub_date': pub_date,
        'tags': 'contemporary classical, new music',
        'excerpt': excerpt,
        'site_id': 'sequenza21',
        'crawl_status': 'success',
        'type': item_type
    })

print(f'Items after filtering: {len(items)}', file=sys.stderr)
for item in items:
    print(f"  - {item['album']} / {item['artist']} ({item['pub_date']}) [{item['type']}]", file=sys.stderr)

with open('/home/liyifan/music-record/2026/05/2026-05-18/sequenza21_reviews.json', 'w') as f:
    json.dump(items, f, indent=2, ensure_ascii=False)

print(f'Written {len(items)} items', file=sys.stderr)
if not items:
    print('No items found in 3-day window — output empty array', file=sys.stderr)