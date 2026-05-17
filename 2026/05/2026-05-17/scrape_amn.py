#!/usr/bin/env python3
import json
import re
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dp
import sys

SITE = "avant_music_news"
SITE_ID = "avantmusicnews"
TAGS = ["experimental", "weird", "progressive", "avant-garde"]
OUTPUT_PATH = "/home/liyifan/music-record/2026/05/2026-05-17/avant_music_news_reviews.json"
FEED_URL = "https://avantmusicnews.com/feed/"

now_utc = datetime.now(timezone.utc)
cutoff_ts = (now_utc.timestamp() - 3 * 86400)

d = feedparser.parse(FEED_URL)
print(f"RSS total entries: {len(d.entries)}")

results = []
skipped = 0
non_music = 0

for e in d.entries:
    pub_str = e.get('published') or e.get('updated') or ''
    if not pub_str:
        skipped += 1
        continue
    try:
        pub_ts = dp.parse(pub_str).astimezone(timezone.utc).timestamp()
    except:
        skipped += 1
        continue

    if pub_ts < cutoff_ts:
        # Stop - entries are in reverse chronological order typically
        # But to be safe, let's continue checking
        pass

    if pub_ts < cutoff_ts:
        continue  # skip old

    title = (e.get('title') or '').strip()
    url = e.get('link') or ''

    # Get full content - try summary_detail or content
    full_text = ''
    if hasattr(e, 'summary_detail') and e.summary_detail:
        full_text = e.summary_detail.get('value', '')
    elif hasattr(e, 'summary') and e.summary:
        full_text = e.summary
    elif e.get('content'):
        full_text = e.content[0].get('value', '')

    # Strip HTML tags for excerpt
    def strip_html(text):
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    plain_text = strip_html(full_text)
    excerpt = plain_text[:500] if plain_text else ''

    # Determine if this is an event listing or a review
    # Event listings have titles like "Coming to X", "This Week at Jazzword"
    # Reviews have "Review" or specific album/artist names

    is_event = False
    is_review_feature = False

    # Event patterns
    event_patterns = [
        r'^Coming to\s',
        r'^This Week at\s',
        r'^(Jazzword|Jazz\.word)',
    ]

    for pat in event_patterns:
        if re.search(pat, title, re.IGNORECASE):
            is_event = True
            break

    # Check if it's a review/feature
    # AMN Reviews: Album/Artist - Review
    review_patterns = [
        r'^AMN Reviews?:?\s',
        r'^Review:?\s',
        r'Review - ',
    ]

    for pat in review_patterns:
        if re.search(pat, title, re.IGNORECASE):
            is_review_feature = True
            break

    # Also check content for review indicators
    content_lower = plain_text.lower()
    has_review_keywords = any(k in content_lower for k in ['review', 'rating', 'score', 'album', 'album of', 'disc of'])

    # Check for score patterns
    score = None
    score_match = re.search(r'(?:rating|score|out of|\/)[:\s]*(\d+(?:\.\d+)?)\s*(?:\/|over\s*)?10', content_lower)
    if score_match:
        try:
            score = float(score_match.group(1))
            if score > 10:  # probably out of 100 or similar
                score = score / 10 if score <= 100 else None
        except:
            score = None

    if is_event:
        print(f"SKIP EVENT: {title}")
        non_music += 1
        continue

    # Try to parse artist/album from title
    artist = ''
    album = ''

    if is_review_feature:
        # Title like "AMN Reviews: FIMAV 2026 Day One"
        remainder = re.sub(r'^AMN Reviews?:?\s*', '', title, flags=re.IGNORECASE)
        # Could be a festival review or album review
        # Try to extract with " - " separator
        if ' – ' in remainder or ' - ' in remainder:
            parts = re.split(r'\s*[\u2013\u2014-]\s*', remainder, 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                album = parts[1].strip()
            else:
                album = remainder
        else:
            album = remainder

    # Non-music filter: skip BLU-RAY, DVD, VOD, UHD etc.
    if any(kw in (artist + album + title).upper() for kw in ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD ']):
        print(f"SKIP NON-MUSIC (video): {title}")
        non_music += 1
        continue

    pub_date_str = ''
    try:
        pub_date_str = dp.parse(pub_str).astimezone(timezone.utc).strftime('%Y-%m-%d')
    except:
        pass

    item_type = "review" if is_review_feature or has_review_keywords else "feature"

    results.append({
        "album": album,
        "artist": artist,
        "score": score,
        "url": url,
        "source": "Avant Music News",
        "pub_date": pub_date_str,
        "tags": TAGS,
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": item_type
    })
    print(f"ADDED [{item_type}]: {title[:60]}")

print(f"\nTotal in window: {len(results)}, skipped old: {skipped}, non-music: {non_music}")

with open(OUTPUT_PATH, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"Written to {OUTPUT_PATH}")