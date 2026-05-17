#!/usr/bin/env python3
"""Scrape Avant Music News - handles RSS + full page content extraction"""
import json
import re
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dp
import sys
import subprocess

SITE = "avant_music_news"
SITE_ID = "avantmusicnews"
TAGS = ["experimental", "weird", "progressive", "avant-garde"]
OUTPUT_PATH = "/home/liyifan/music-record/2026/05/2026-05-17/avant_music_news_reviews.json"
FEED_URL = "https://avantmusicnews.com/feed/"

now_utc = datetime.now(timezone.utc)
cutoff_ts = (now_utc.timestamp() - 3 * 86400)
cutoff_str = (now_utc - datetime.timedelta(days=3)).strftime('%Y-%m-%d')

print(f"Cutoff: {cutoff_str} (ts: {cutoff_ts})")

d = feedparser.parse(FEED_URL)
print(f"RSS total entries: {len(d.entries)}")

# Collect URLs from RSS in the 3-day window
rss_items = []
for e in d.entries:
    pub_str = e.get('published') or e.get('updated') or ''
    if not pub_str:
        continue
    try:
        pub_ts = dp.parse(pub_str).astimezone(timezone.utc).timestamp()
        pub_date_str = dp.parse(pub_str).astimezone(timezone.utc).strftime('%Y-%m-%d')
    except:
        continue
    if pub_ts < cutoff_ts:
        continue
    rss_items.append({
        'title': e.get('title', '').strip(),
        'url': e.get('link', ''),
        'pub_date': pub_date_str,
        'pub_str': pub_str,
    })

print(f"Items in 3-day window: {len(rss_items)}")

# For each RSS item, fetch the actual page to get full content
# Use web_extract tool approach via execute_code
from hermes_tools import web_extract

results = []

for item in rss_items:
    url = item['url']
    title = item['title']
    pub_date = item['pub_date']

    # Event pattern detection
    is_event = False
    event_patterns = [
        r'^Coming to\s',
        r'^This Week at\s',
        r'^Jazzword',
        r'^CKCU',
        r'^Rabble Without A Cause Show',
    ]
    for pat in event_patterns:
        if re.search(pat, title, re.IGNORECASE):
            print(f"SKIP EVENT: {title}")
            is_event = True
            break
    if is_event:
        continue

    # Fetch the page content
    print(f"Fetching: {url}")
    try:
        result = web_extract(urls=[url])
        content_data = result.get('results', [{}])[0]
        content = content_data.get('content', '') or ''
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        content = ''

    # Extract artist/album from content
    # For roundup pages like Dusted Reviews, Chain D.L.K., Psychotropic Wonderland
    # these list multiple album reviews
    #
    # Pattern: Artist – "Album" (Label) reviewed by Reviewer
    # or: Artist, "Album" (Label) reviewed by

    def strip_html(text):
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&\w+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    plain = strip_html(content)

    # Determine if it's a roundup/aggregation or a single review
    # Roundup patterns: multiple "reviewed by" or multiple album entries
    is_roundup = bool(re.search(r'reviewed by', plain, re.IGNORECASE))

    if is_roundup:
        # Parse each individual review from roundup
        # Pattern: Artist – "Album" (Label) reviewed by Reviewer on Date
        # or: Artist, "Album" (Label) — reviewed by
        review_patterns = [
            r'([A-Z][^"\n]+?)\s*[-–—]\s*"?([^"\n]+?)"?\s*\(([^)\n]+)\)\s*(?:reviewed by|—|–)',
            r'([A-Z][^"\n]+?)\s*[-–—]\s*"?([^"\n]+?)"?\s*reviewed by',
        ]
        found_any = False
        for pat in review_patterns:
            matches = re.findall(pat, plain, re.IGNORECASE)
            for m in matches:
                if len(m) >= 3:
                    artist = m[0].strip()
                    album = m[1].strip()
                    label = m[2].strip()
                    # Skip non-music
                    if any(kw in (artist + album).upper() for kw in ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD', 'VHS']):
                        continue
                    # Skip concert listings, show announcements
                    if any(kw in album.lower() for kw in ['concert', 'show', 'tour', 'festival', 'june', 'may ', 'april', '2026']):
                        # Check if it's a release date or listing
                        if re.search(r'(June|May|April)\s+\d', album):
                            continue
                    # Try to find a score
                    score = None
                    score_patterns = [
                        r'(?:rating|score|out of)[:\s]*(\d+(?:\.\d+)?)\s*/\s*10',
                        r'\((\d+(?:\.\d+)?)\s*/\s*10\)',
                    ]
                    for sp in score_patterns:
                        sm = re.search(sp, artist + ' ' + album, re.IGNORECASE)
                        if sm:
                            try:
                                score = float(sm.group(1))
                                if score > 10: score = score / 10
                            except:
                                pass

                    excerpt = f"{artist} – {album} ({label})"
                    results.append({
                        "album": album,
                        "artist": artist,
                        "score": score,
                        "url": url,
                        "source": "Avant Music News",
                        "pub_date": pub_date,
                        "tags": TAGS,
                        "excerpt": excerpt,
                        "site_id": SITE_ID,
                        "crawl_status": "success",
                        "type": "review"
                    })
                    found_any = True
                    print(f"  ROUNDUP REVIEW: {artist} – {album}")

        if not found_any:
            # Try a simpler pattern: just look for quoted album names
            album_matches = re.findall(r'"([^"]+)"\s*\(([^)]+)\)\s*(?:reviewed by|—|–)', plain)
            for am in album_matches:
                album = am[0].strip()
                label = am[1].strip()
                # Artist is usually in the same paragraph before the quote
                # Try to find the preceding text
                context_pattern = rf'([A-Z][^"\n]{{0,60}}?)\s*"?{re.escape(album)}"?'
                ctx_m = re.search(context_pattern, plain, re.IGNORECASE)
                artist = ctx_m.group(1).strip() if ctx_m else ''
                if len(artist) > 100:
                    artist = ''
                if any(kw in album.upper() for kw in ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']):
                    continue
                if artist:
                    results.append({
                        "album": album,
                        "artist": artist,
                        "score": None,
                        "url": url,
                        "source": "Avant Music News",
                        "pub_date": pub_date,
                        "tags": TAGS,
                        "excerpt": f"{artist} – {album} ({label})",
                        "site_id": SITE_ID,
                        "crawl_status": "success",
                        "type": "review"
                    })
                    found_any = True
                    print(f"  ROUNDUP REVIEW (alt): {artist} – {album}")

        if not found_any:
            # No sub-items extracted - treat the whole page as a feature
            excerpt = plain[:500] if plain else ''
            results.append({
                "album": title,
                "artist": "",
                "score": None,
                "url": url,
                "source": "Avant Music News",
                "pub_date": pub_date,
                "tags": TAGS,
                "excerpt": excerpt,
                "site_id": SITE_ID,
                "crawl_status": "success",
                "type": "feature"
            })
            print(f"  No sub-items found, saved as feature: {title[:50]}")
    else:
        # Single article - extract info from title and content
        # Try to parse artist - album from title
        artist = ''
        album = ''

        title_clean = re.sub(r'^AMN Reviews:?\s*', '', title, flags=re.IGNORECASE)

        # Check for " - " or " – " separator
        if ' – ' in title_clean or ' - ' in title_clean:
            parts = re.split(r'\s*[\u2013\u2014-]\s*', title_clean, 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                album = parts[1].strip()

        # Try to find score in content
        score = None
        score_patterns = [
            r'(?:rating|score|out of)[:\s]*(\d+(?:\.\d+)?)\s*/\s*10',
            r'\b(\d+(?:\.\d+)?)\s*/\s*10\b',
        ]
        for sp in score_patterns:
            sm = re.search(sp, content[:2000], re.IGNORECASE)
            if sm:
                try:
                    score = float(sm.group(1))
                    if score > 10: score = score / 10
                except:
                    pass

        excerpt = plain[:500] if plain else ''

        # Check for video/non-music keywords
        if any(kw in (artist + album + title).upper() for kw in ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']):
            print(f"SKIP NON-MUSIC: {title}")
            continue

        item_type = "review" if artist and album else "feature"

        results.append({
            "album": album or title,
            "artist": artist,
            "score": score,
            "url": url,
            "source": "Avant Music News",
            "pub_date": pub_date,
            "tags": TAGS,
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": item_type
        })
        print(f"  {'REVIEW' if item_type == 'review' else 'FEATURE'}: {title[:60]}")

# Deduplicate by url+album
seen = set()
deduped = []
for r in results:
    key = (r['url'], r.get('album', ''), r.get('artist', ''))
    if key not in seen:
        seen.add(key)
        deduped.append(r)

print(f"\nTotal items after dedup: {len(deduped)}")
for r in deduped:
    print(f"  {r['type']}: {r['artist']} - {r['album']}")

with open(OUTPUT_PATH, 'w') as f:
    json.dump(deduped, f, indent=2, ensure_ascii=False)
print(f"Written to {OUTPUT_PATH}")