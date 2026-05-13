#!/usr/bin/env python3
"""RSS-based scraper for music review sites"""

import json
import os
import subprocess
import re
from datetime import datetime, timedelta
import feedparser

OUTPUT_DIR = "/home/liyifan/music-record/2026/05/2026-05-14/"
DATE_FROM = datetime(2026, 5, 7)
DATE_TO = datetime(2026, 5, 14)

def parse_date(date_str):
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except:
        pass
    formats = ["%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            pass
    return None

def is_recent(date_obj):
    if date_obj is None:
        return False
    return DATE_FROM <= date_obj <= DATE_TO

def parse_title_artist(title):
    if not title:
        return "", ""
    patterns = [
        r'^(.+?)\s*[-:–]\s*(.+)$',
        r'^(.+?)\s+by\s+(.+)$',
        r'^(.+?)\s*\|\s*(.+)$',
    ]
    for pattern in patterns:
        m = re.match(pattern, title.strip())
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return title.strip(), ""

def clean_excerpt(html):
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500] if len(text) > 500 else text

def scrape_feed(site_id, feed_url, tags):
    reviews = []
    try:
        result = subprocess.run(
            ['curl', '-s', '-L', '--max-time', '30', '-A', 'Mozilla/5.0', feed_url],
            capture_output=True, text=True, timeout=35
        )
        if result.returncode != 0 or not result.stdout:
            print(f"  Curl failed for {site_id}")
            return []

        feed = feedparser.parse(result.stdout)
        for entry in feed.entries:
            try:
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    t = entry.published_parsed
                    if t:
                        pub_date = datetime(t.tm_year, t.tm_mon, t.tm_mday)

                if not is_recent(pub_date):
                    continue

                title = entry.get('title', '')
                album, artist = parse_title_artist(title)

                link = entry.get('link', '')

                excerpt = ""
                if hasattr(entry, 'summary'):
                    excerpt = clean_excerpt(entry.summary)
                elif hasattr(entry, 'description'):
                    excerpt = clean_excerpt(entry.description)

                review = {
                    "album": album,
                    "artist": artist,
                    "score": None,
                    "url": link,
                    "source": site_id,
                    "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else None,
                    "tags": tags,
                    "excerpt": excerpt,
                    "site_id": site_id,
                    "crawl_status": "success"
                }
                reviews.append(review)
            except Exception as e:
                continue

    except Exception as e:
        print(f"  Error: {e}")
    return reviews

def write_output(site_id, reviews, status="success"):
    output = {
        "site_id": site_id,
        "crawl_status": status,
        "reviews": reviews,
        "count": len(reviews),
        "date_range": f"{DATE_FROM.strftime('%Y-%m-%d')} to {DATE_TO.strftime('%Y-%m-%d')}"
    }
    filepath = os.path.join(OUTPUT_DIR, f"{site_id}_reviews.json")
    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  -> {site_id}: {len(reviews)} reviews")
    return len(reviews)

# Sites with working RSS
RSS_SITES = {
    "attn_magazine": {
        "name": "ATTN:Magazine",
        "feed_url": "https://www.attnmagazine.co.uk/feed/",
        "tags": ["experimental music", "sound art", "longform criticism"]
    },
    "hhv_mag": {
        "name": "HHV Mag",
        "feed_url": "https://www.hhv-mag.com/feed/",
        "tags": ["electronic", "vinyl culture", "electroacoustic"]
    },
    "new_music_buff": {
        "name": "New Music Buff",
        "feed_url": "https://newmusicbuff.com/feed/",
        "tags": ["contemporary", "electroacoustic", "new music"]
    },
}

# Sites with broken/inaccessible RSS (need browser_navigate)
BROKEN_RSS = [
    "rest_is_noise_ph", "mixmag_asia", "chain_dlk", "musique_machine",
    "strangely_isolated_place", "jazz_trail", "truth_and_lies_music",
    "jazz_journal", "five_against_four", "modern_classical_music",
    "the_classic_review", "froots", "roots_world", "progressor",
    "prog_mistress", "wild_city", "bandwagon_asia", "hear65"
]

def main():
    print("=== RSS Scraping Phase ===\n")
    total = 0

    for site_id, config in RSS_SITES.items():
        print(f"Scraping {config['name']}...")
        reviews = scrape_feed(site_id, config['feed_url'], config['tags'])
        write_output(site_id, reviews)
        total += len(reviews)

    # Create empty outputs for browser_navigate sites
    print("\n=== Browser Navigate Sites (will be handled separately) ===\n")
    for site_id in BROKEN_RSS:
        write_output(site_id, [], "pending_browser_navigate")

    print(f"\n=== RSS Phase Complete: {total} reviews ===")

if __name__ == "__main__":
    main()