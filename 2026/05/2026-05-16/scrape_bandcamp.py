#!/usr/bin/env python3
"""
Scrape Bandcamp Daily - RSS + article page extraction
Time window: 3 days
"""
import feedparser
from dateutil import parser as dateparser
from datetime import datetime, timezone, timedelta
import json
import re
import sys
import os
import html
from urllib.parse import urljoin

# ── config ──────────────────────────────────────────────────────────────────
RSS_URL = "https://daily.bandcamp.com/feed"
SITE_ID = "bandcamp_daily"
SOURCE  = "Bandcamp Daily"
TAGS     = ["experimental", "electronic", "world", "ambient", "scene-specific"]
CUTOFF_DAYS = 3
OUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-16/bandcamp_daily_reviews.json"

# ── helpers ───────────────────────────────────────────────────────────────────

NON_MUSIC_KEYWORDS = [
    r"\(BLU-RAY\)", r"\(BLU RAY\)", r"\(UHD\)", r"\(VOD\)", r"\(DVD\)",
    r"BLU-RAY", r"UHD", r"\bDVD\b", r"\bVOD\b",
    r"\bFILM\b", r"\bMOVIE\b", r"\bDOCUMENTARY\b",
]

def is_non_music(title: str, album: str = "") -> bool:
    text = f"{title} {album}".upper()
    for kw in NON_MUSIC_KEYWORDS:
        if re.search(kw, text, re.IGNORECASE):
            return True
    return False

def parse_pub_date(pub_str: str) -> datetime:
    """Parse RSS pubDate to UTC datetime."""
    try:
        dt = dateparser.parse(pub_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None

def age_days(pub_str: str) -> float:
    """Return article age in days from now."""
    dt = parse_pub_date(pub_str)
    if dt is None:
        return 999
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 86400

def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_excerpt_from_summary(summary: str, max_chars: int = 500) -> str:
    """Strip HTML from RSS summary, return first max_chars."""
    raw = strip_html(summary)
    return raw[:max_chars]

def determine_type(url: str, title: str) -> str:
    """review or feature."""
    # Bandcamp Daily URL patterns
    if re.search(r'/album-of-the-day/', url):
        return "review"
    if re.search(r'/reviews?/', url):
        return "review"
    # features, lists, big-ups, scene-reports, label-profiles, etc. → feature
    return "feature"

def parse_review_page_curl(url: str) -> dict:
    """Fetch article page with curl, extract structured data."""
    import subprocess
    result = {}
    result['url'] = url

    try:
        proc = subprocess.run(
            ['curl', '-s', '-L', '--connect-timeout', '10', '-m', '30', url],
            capture_output=True, text=True, timeout=35
        )
        html_content = proc.stdout
    except Exception as e:
        result['error'] = str(e)
        return result

    # Extract article title
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.DOTALL)
    if title_match:
        result['article_title'] = strip_html(title_match.group(1))[:300]

    # Extract author - look for "Review by" or "by"
    author_match = re.search(r'Review by\s+([^\n<]+)', html_content)
    if not author_match:
        author_match = re.search(r'by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', html_content)
    if author_match:
        result['author'] = strip_html(author_match.group(1).strip())

    # Extract date
    date_match = re.search(r'([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', html_content)
    if date_match:
        result['date_str'] = date_match.group(1)

    # Extract score - look for "X/10" or "X out of 10" or rating numbers
    score_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:/|out of)\s*10', html_content)
    if score_match:
        try:
            result['score'] = float(score_match.group(1))
        except:
            pass

    # Look for album/artist in the page - usually in structured data or headings
    # Try JSON-LD
    json_ld = re.search(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                        html_content, re.DOTALL)
    if json_ld:
        try:
            import json as json_mod
            data = json_mod.loads(json_ld.group(1))
            if isinstance(data, dict):
                result['jsonld_artist'] = data.get('author', {}).get('name', '')
                result['jsonld_name'] = data.get('name', '')
        except:
            pass

    # Extract article body text for excerpt
    body_match = re.search(
        r'<article[^>]*>(.*?)</article>', html_content, re.DOTALL
    )
    if body_match:
        body_html = body_match.group(1)
        # Remove nav, header, footer, script, style
        body_html = re.sub(r'<script[^>]*>.*?</script>', '', body_html, flags=re.DOTALL)
        body_html = re.sub(r'<style[^>]*>.*?</style>', '', body_html, flags=re.DOTALL)
        body_text = strip_html(body_html)
        result['excerpt'] = body_text[:500] if body_text else ''

    return result

def article_title_to_album_artist(title: str) -> tuple:
    """Parse 'Artist, \"Album Name\"' format into (album, artist)."""
    # Pattern: "Artist, \"Album Name\""
    m = re.match(r'^(.+?),\s*["""](.+?)["""]\s*$', title)
    if m:
        return m.group(2).strip(), m.group(1).strip()

    # Pattern: "Artist – \"Album Name\""
    m = re.match(r'^(.+?)\s*[-–]\s*["""](.+?)["""]\s*$', title)
    if m:
        return m.group(2).strip(), m.group(1).strip()

    return title, ""


# ── main scraping logic ───────────────────────────────────────────────────────

def main():
    now_utc = datetime.now(timezone.utc)
    cutoff  = now_utc - timedelta(days=CUTOFF_DAYS)

    print(f"[{now_utc.isoformat()}] Scraping Bandcamp Daily")
    print(f"Cutoff: {cutoff.isoformat()} (3 days ago)")

    # 1. Parse RSS
    print("Fetching RSS feed...")
    d = feedparser.parse(RSS_URL)
    print(f"RSS entries: {len(d.entries)}")

    # 2. Filter entries within 3 days
    recent = []
    for e in d.entries:
        pub = e.get('published', '')
        days = age_days(pub)
        print(f"  {days:.1f}d: {e.get('title','')[:80]}")
        if days <= CUTOFF_DAYS:
            recent.append((e, days))

    print(f"\nRecent entries (≤{CUTOFF_DAYS} days): {len(recent)}")

    if not recent:
        print("No recent articles. Writing empty output.")
        with open(OUT_FILE, 'w') as f:
            json.dump([], f)
        return

    # 3. Process each article
    results = []
    for e, days in recent:
        url = e.get('link', '')
        raw_title = e.get('title', '')
        pub_date_str = e.get('published', '')
        pub_date = parse_pub_date(pub_date_str)

        # Skip non-music
        album, artist = article_title_to_album_artist(raw_title)
        if is_non_music(raw_title, album):
            print(f"  SKIP (non-music): {raw_title[:80]}")
            continue

        # Get excerpt from RSS summary
        summary = e.get('summary', e.get('description', ''))
        excerpt = extract_excerpt_from_summary(summary)

        # Determine type
        doc_type = determine_type(url, raw_title)

        # Try to get score from article page
        score = None
        article_excerpt = None

        # For reviews, try to parse article page for more detail
        if doc_type == "review":
            page_data = parse_review_page_curl(url)
            score = page_data.get('score')
            if not article_excerpt:
                article_excerpt = page_data.get('excerpt', '')
            if not artist and page_data.get('jsonld_artist'):
                artist = page_data.get('jsonld_artist')
            if not album and page_data.get('jsonld_name'):
                album = page_data.get('jsonld_name')

        # Use article excerpt if we got one
        if article_excerpt:
            excerpt = article_excerpt

        item = {
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date.strftime('%Y-%m-%d') if pub_date else None,
            "tags": TAGS,
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": doc_type,
        }
        results.append(item)
        print(f"  {'[REVIEW]' if doc_type=='review' else '[FEATURE]'} {raw_title[:80]}")

    # 4. Write output
    print(f"\nTotal items: {len(results)}")
    with open(OUT_FILE, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Written to: {OUT_FILE}")

    return results

if __name__ == '__main__':
    main()
