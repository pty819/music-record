import feedparser
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import re
import json

cutoff = datetime.now(timezone.utc) - timedelta(days=3)
print("Cutoff:", cutoff)

feed = feedparser.parse("https://worldmusiccentral.org/feed/")
print("Total entries:", len(feed.entries))

def parse_wmc_date(date_str):
    """Parse pubDate like 'Fri, 15 May 2026 10:36:34 +0000'"""
    from email.utils import parsedate_to_datetime
    return parsedate_to_datetime(date_str)

def strip_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def get_excerpt(entry):
    """Get full text from description, prefer summary if available."""
    # Try content:encoded first (full HTML content)
    content_enc = getattr(entry, 'content_encoded', None) or getattr(entry, 'content', None)
    if content_enc:
        val = content_enc[0].value if hasattr(content_enc[0], 'value') else str(content_enc[0])
        text = strip_html(val)
        return text[:500] if text else ""

    # Fall back to description
    desc = getattr(entry, 'description', None) or getattr(entry, 'summary', None)
    if desc:
        text = strip_html(desc)
        return text[:500] if text else ""

    return ""

# Check for album review category
def is_album_review(entry):
    cats = [getattr(c, 'term', str(c)) for c in getattr(entry, 'tags', [])]
    for cat in cats:
        if 'album review' in cat.lower():
            return True
    return False

def is_non_music_filtered(entry):
    """Check if title or artist contains non-music keywords."""
    title = getattr(entry, 'title', '') or ''
    desc = getattr(entry, 'description', '') or ''

    non_music = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    combined = title + ' ' + desc
    for nm in non_music:
        if nm.lower() in combined.lower():
            return True
    return False

recent_items = []
for e in feed.entries:
    try:
        pub_dt = parse_wmc_date(e.published)
    except:
        pub_dt = None

    if pub_dt and pub_dt >= cutoff:
        recent_items.append((pub_dt, e))

print(f"Recent (within 3 days): {len(recent_items)}")

results = []
for pub_dt, e in recent_items:
    print(f"\n  {pub_dt.date()}: {e.title[:70]}")
    print(f"    link: {e.link}")

    cats = [getattr(c, 'term', str(c)) for c in getattr(e, 'tags', [])]
    print(f"    categories: {cats}")

    # Check if album review
    album_review = is_album_review(e)

    # Extract album and artist from title
    title = e.title
    album = None
    artist = None

    if album_review:
        # Typical format: "Artist – Album Name" or "Album Name by Artist"
        if ' – ' in title:
            parts = title.split(' – ', 1)
            artist = parts[0].strip()
            album = parts[1].strip()
        elif ' by ' in title.lower():
            match = re.search(r'(.+?)\s+by\s+(.+)', title, re.IGNORECASE)
            if match:
                album = match.group(1).strip()
                artist = match.group(2).strip()

    # Get excerpt / full text
    excerpt = get_excerpt(e)
    if not excerpt:
        excerpt = strip_html(getattr(e, 'description', '') or '')[:500]

    # Extract score (look for rating text)
    score = None
    excerpt_text = excerpt.lower()
    # Look for patterns like "8/10", "4 out of 5", "out of 10"
    score_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:/10|out of 10)', excerpt)
    if score_match:
        score = float(score_match.group(1))
    else:
        score_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:/5|out of 5|out of five)', excerpt)
        if score_match:
            score = float(score_match.group(1)) * 2  # Convert to /10

    item_type = "review" if album_review else "feature"

    item = {
        "album": album,
        "artist": artist,
        "score": score,
        "url": e.link,
        "source": "World Music Central",
        "pub_date": pub_dt.strftime("%Y-%m-%d"),
        "tags": [getattr(c, 'term', str(c)) for c in getattr(e, 'tags', [])],
        "excerpt": excerpt,
        "site_id": "world_music_central",
        "crawl_status": "success",
        "type": item_type,
    }
    results.append(item)
    print(f"    type: {item_type}, album: {album}, artist: {artist}, score: {score}")
    print(f"    excerpt preview: {excerpt[:100]}...")

print(f"\n\nTotal items to write: {len(results)}")
print("JSON preview:")
print(json.dumps(results, indent=2, ensure_ascii=False)[:2000])