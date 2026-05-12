#!/usr/bin/env python3
"""Scrape ProgressoR site for album reviews (last 7 days only)."""
import urllib.request
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

SITE_ID = "progressor"
TAGS = ["art-rock", "prog", "jazz-fusion"]
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-13/progressor_reviews.json"
NOW = datetime.now()
SEVEN_DAYS_AGO = NOW - timedelta(days=7)

def is_recent(pub_date_str):
    """Return True if pub_date is within 7 days."""
    try:
        dt = parsedate_to_datetime(pub_date_str)
        dt_naive = dt.replace(tzinfo=None)
        return (NOW - dt_naive).days <= 7
    except:
        return False

def scrape_feed():
    """Try RSS feed first."""
    url = 'https://www.progressor.net/feed/'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        entries = root.findall('channel/item')
        print(f"RSS feed: found {len(entries)} entries")

        reviews = []
        for item in entries:
            pub = item.find('pubDate')
            if pub is None or not is_recent(pub.text):
                continue

            title_el = item.find('title')
            link_el = item.find('link')
            desc_el = item.find('description')

            title = title_el.text if title_el is not None else ""
            link = link_el.text if link_el is not None else ""
            excerpt = desc_el.text if desc_el is not None else ""

            # Clean HTML from excerpt
            if excerpt:
                excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()
                excerpt = excerpt[:500] if len(excerpt) > 500 else excerpt

            # Parse album/artist from title (usually "Album - Artist" or "Artist - Album")
            album = ""
            artist = ""
            if " - " in title:
                parts = title.split(" - ", 1)
                artist = parts[0].strip()
                album = parts[1].strip()
            else:
                album = title

            # Try to find score in description
            score = None
            score_match = re.search(r'(\d+)/10', excerpt)
            if score_match:
                score = int(score_match.group(1))

            reviews.append({
                "album": album,
                "artist": artist,
                "score": score,
                "url": link,
                "source": "ProgressoR",
                "pub_date": pub.text,
                "tags": TAGS,
                "excerpt": excerpt,
                "site_id": SITE_ID,
                "crawl_status": "fresh"
            })

        print(f"RSS feed: {len(reviews)} recent reviews")
        return reviews
    except Exception as e:
        print(f"RSS failed: {e}")
        return None

def scrape_browser():
    """Fallback: browse with headless browser."""
    print("Falling back to browser scraping...")
    return []

if __name__ == "__main__":
    reviews = scrape_feed()

    if reviews is None:
        print("No reviews found (RSS failed or no recent items)")
        reviews = []

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

    print(f"Written {len(reviews)} reviews to {OUTPUT_FILE}")
    print(f"pub_date cutoff: {SEVEN_DAYS_AGO.isoformat()}")