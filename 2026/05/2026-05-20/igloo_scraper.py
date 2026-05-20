import feedparser
import json
import re
from datetime import datetime, timedelta
from html import unescape

SITE_URL = "https://igloomag.com"
FEED_URL = "https://igloomag.com/feed"
TAGS = ["experimental electronic", "IDM", "ambient", "glitch", "electroacoustic"]
SITE_ID = "igloo_magazine"
CUTOFF_DAYS = 3

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    return text.strip()

def parse_igloo():
    feed = feedparser.parse(FEED_URL)
    cutoff = datetime.now() - timedelta(days=CUTOFF_DAYS)
    
    items = []
    for e in feed.entries:
        pub = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        if not pub:
            continue
        pub_dt = datetime(*pub[:6])
        if pub_dt < cutoff:
            continue
        
        title = e.get("title", "")
        link = e.get("link", "")
        published = getattr(e, "published", "")
        
        # Get full summary from RSS
        summary = getattr(e, "summary", "") or ""
        if isinstance(summary, list):
            summary = summary[0].get("value", "") if summary else ""
        elif isinstance(summary, dict):
            summary = summary.get("value", "")
        summary = strip_html(summary)
        excerpt = summary[:500] if summary else ""
        
        # Determine type from URL path
        if "/features/" in link or "/interviews/" in link or "/podcasts/" in link:
            item_type = "feature"
        else:
            item_type = "review"
        
        # Parse album/artist from title (format: "Artist :: Album (Label)" or "Artist :: Album — [concise]")
        album = ""
        artist = ""
        
        if "::" in title:
            parts = title.split("::", 1)
            artist = parts[0].strip()
            remainder = parts[1].strip()
            
            # Remove trailing "[concise]" marker
            remainder = re.sub(r'\s*—\s*\[concise\]\s*$', '', remainder)
            remainder = re.sub(r'\s*\[concise\]\s*$', '', remainder)
            
            # Remove label in parentheses
            label_match = re.search(r'\(([^)]+)\)$', remainder)
            if label_match:
                album = remainder[:label_match.start()].strip()
            else:
                album = remainder
        else:
            # No "::" - try to split on " — " or " – "
            dash_match = re.search(r'\s+[\u2014\u2013]\s+', title)
            if dash_match:
                artist = title[:dash_match.start()].strip()
                album = title[dash_match.end():].strip()
                # Remove trailing (label)
                label_match = re.search(r'\(([^)]+)\)$', album)
                if label_match:
                    album = album[:label_match.start()].strip()
            else:
                album = title
        
        # For V/A compilations, artist stays "V/A"
        # If album has "/" in it (like "memorysound/Fading Bright & Spectrical/Litchfield"), it may be a split/compilation
        # Keep artist as-is for now
        
        # Skip non-music (BLU-RAY, DVD, etc.)
        skip_keywords = ["BLU-RAY", "BLU RAY", "UHD", "VOD", "DVD"]
        combined = (artist + " " + album).upper()
        if any(kw in combined for kw in skip_keywords):
            print(f"SKIP (non-music): {title}")
            continue
        
        # For feature type, put title in album, keep artist or use category
        if item_type == "feature":
            album = title
            artist = ""
        
        item = {
            "album": album,
            "artist": artist,
            "score": None,
            "url": link,
            "source": SITE_URL,
            "pub_date": published,
            "tags": TAGS,
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": item_type,
        }
        print(f"TYPE={item_type}: {artist} :: {album} | {published}")
        items.append(item)
    
    return items

items = parse_igloo()
print(f"\nTotal items: {len(items)}")
with open("/home/liyifan/music-record/2026/05/2026-05-20/igloo_magazine_reviews.json", "w") as f:
    json.dump(items, f, indent=2, ensure_ascii=False)
print("Written to igloo_magazine_reviews.json")
