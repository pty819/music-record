#!/usr/bin/env python3
"""Music review scraper for 21 sites - batch task for 2026-05-14"""

import json
import os
import sys
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

# Output directory
OUTPUT_DIR = "/home/liyifan/music-record/2026/05/2026-05-14/"

# Date range: last 7 days (2026-05-07 to 2026-05-14)
DATE_FROM = datetime(2026, 5, 7)
DATE_TO = datetime(2026, 5, 14)

def parse_date(date_str):
    """Try parsing various date formats"""
    if not date_str:
        return None
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            pass
    # Try common patterns
    patterns = [
        r'(\d{4})-(\d{2})-(\d{2})',
        r'(\d{1,2})\s+(\w+)\s+(\d{4})',
    ]
    for pattern in patterns:
        m = re.search(pattern, date_str)
        if m:
            try:
                if pattern == r'(\d{4})-(\d{2})-(\d{2})':
                    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except:
                pass
    return None

def is_recent(date_obj):
    """Check if date is within last 7 days"""
    if date_obj is None:
        return False
    return DATE_FROM <= date_obj <= DATE_TO

def create_empty_output(site_id):
    """Create empty JSON output for a site"""
    return {
        "site_id": site_id,
        "crawl_status": "success",
        "reviews": [],
        "count": 0,
        "date_range": f"{DATE_FROM.strftime('%Y-%m-%d')} to {DATE_TO.strftime('%Y-%m-%d')}"
    }

def write_output(site_id, data, status="success", error=None):
    """Write output JSON file"""
    output = {
        "site_id": site_id,
        "crawl_status": status,
        "reviews": data,
        "count": len(data),
        "date_range": f"{DATE_FROM.strftime('%Y-%m-%d')} to {DATE_TO.strftime('%Y-%m-%d')}"
    }
    if error:
        output["error"] = error
    
    filepath = os.path.join(OUTPUT_DIR, f"{site_id}_reviews.json")
    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  -> {filepath}: {len(data)} reviews, status={status}")
    return len(data)

# Site configurations from sites.json
SITES = {
    "rest_is_noise_ph": {
        "name": "The Rest Is Noise PH",
        "url": "https://therestisnoiseph.com/",
        "strategy": "playwright_headless",
        "tags": ["asian", "experimental", "alternative"]
    },
    "mixmag_asia": {
        "name": "Mixmag Asia",
        "url": "https://mixmag.asia/category/reviews",
        "strategy": "playwright_headless",
        "tags": ["asian electronic", "ambient", "experimental"]
    },
    "attn_magazine": {
        "name": "ATTN:Magazine",
        "url": "https://www.attnmagazine.co.uk/",
        "rss_url": "https://www.attnmagazine.co.uk/feed/",
        "strategy": "http_get",
        "tags": ["experimental music", "sound art", "longform criticism"]
    },
    "chain_dlk": {
        "name": "The Chain D.L.K.",
        "url": "https://www.chaindlk.com/",
        "rss_url": "https://www.chaindlk.com/feed/",
        "strategy": "http_get",
        "tags": ["industrial", "dark ambient", "glitch", "avant-garde"]
    },
    "musique_machine": {
        "name": "Musique Machine",
        "url": "https://www.musiquemachine.com/",
        "strategy": "playwright_headless",
        "tags": ["dark ambient", "industrial", "electroacoustic"]
    },
    "hhv_mag": {
        "name": "HHV Mag",
        "url": "https://www.hhv-mag.com/",
        "rss_url": "https://www.hhv-mag.com/feed/",
        "strategy": "http_get",
        "tags": ["electronic", "vinyl culture", "electroacoustic"]
    },
    "strangely_isolated_place": {
        "name": "A Strangely Isolated Place",
        "url": "https://www.astrangelyisolatedplace.com/",
        "strategy": "playwright_headless",
        "tags": ["ambient", "electronica", "modern classical"]
    },
    "new_music_buff": {
        "name": "New Music Buff",
        "url": "https://newmusicbuff.com/",
        "rss_url": "https://newmusicbuff.com/feed/",
        "strategy": "http_get",
        "tags": ["contemporary", "electroacoustic", "new music"]
    },
    "jazz_trail": {
        "name": "JazzTrail",
        "url": "https://jazztrail.net/",
        "strategy": "playwright_headless",
        "tags": ["avant jazz", "modern jazz"]
    },
    "truth_and_lies_music": {
        "name": "Truth & Lies Music",
        "url": "https://www.truthandliesmusic.com/",
        "strategy": "playwright_headless",
        "tags": ["free jazz", "improvised music", "adventurous jazz"]
    },
    "jazz_journal": {
        "name": "Jazz Journal",
        "url": "https://jazzjournal.co.uk/",
        "strategy": "playwright_headless",
        "tags": ["jazz", "reviews"]
    },
    "five_against_four": {
        "name": "5:4",
        "url": "https://5against4.com/",
        "rss_url": "https://5against4.com/feed/",
        "strategy": "http_get",
        "tags": ["modern classical", "electronic", "experimental", "innovative music"]
    },
    "modern_classical_music": {
        "name": "Modern Classical Music",
        "url": "https://www.modernclassicalmusic.com/",
        "rss_url": "https://www.modernclassicalmusic.com/feed/",
        "strategy": "http_get",
        "tags": ["modern classical", "contemporary composition"]
    },
    "the_classic_review": {
        "name": "The Classic Review",
        "url": "https://theclassicreview.com/",
        "strategy": "playwright_headless",
        "tags": ["classical", "contemporary"]
    },
    "froots": {
        "name": "fRoots",
        "url": "https://frootsmag.com/",
        "rss_url": "https://frootsmag.com/feed/",
        "strategy": "http_get",
        "tags": ["folk", "roots", "world music"]
    },
    "roots_world": {
        "name": "RootsWorld",
        "url": "https://www.rootsworld.com/",
        "strategy": "playwright_headless",
        "tags": ["world music", "roots", "folk"]
    },
    "progressor": {
        "name": "ProgressoR",
        "url": "https://www.progressor.net/",
        "strategy": "playwright_headless",
        "tags": ["art-rock", "prog", "jazz-fusion"]
    },
    "prog_mistress": {
        "name": "Prog Mistress",
        "url": "https://progmistress.com/",
        "strategy": "playwright_headless",
        "tags": ["prog", "jazz-rock", "fusion"]
    },
    "wild_city": {
        "name": "Wild City",
        "url": "https://www.thewildcity.com/",
        "strategy": "playwright_headless",
        "tags": ["south asian", "alternative", "electronic"]
    },
    "bandwagon_asia": {
        "name": "Bandwagon Asia",
        "url": "https://www.bandwagon.asia/",
        "strategy": "playwright_headless",
        "tags": ["asia music", "reviews", "interviews"]
    },
    "hear65": {
        "name": "Hear65",
        "url": "https://hear65.bandwagon.asia/",
        "strategy": "playwright_headless",
        "tags": ["singapore music", "reviews"]
    }
}

def scrape_with_curl(site_id, url, rss_url=None):
    """Scrape using curl + feedparser for RSS sites"""
    import feedparser
    
    feed_url = rss_url if rss_url else url
    if not feed_url:
        return []
    
    reviews = []
    try:
        import subprocess
        import xml.etree.ElementTree as ET
        
        # Fetch the feed
        result = subprocess.run(
            ['curl', '-s', '-L', '--max-time', '30', feed_url],
            capture_output=True,
            text=True,
            timeout=35
        )
        
        if result.returncode != 0 or not result.stdout:
            print(f"  Curl failed for {site_id}")
            return []
        
        # Parse with feedparser
        feed = feedparser.parse(result.stdout)
        
        for entry in feed.entries:
            try:
                # Get date
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    from time import struct_time
                    t = entry.published_parsed
                    if t:
                        pub_date = datetime(t.tm_year, t.tm_mon, t.tm_mday)
                
                if not is_recent(pub_date):
                    continue
                
                # Get title - parse album/artist from title
                title = entry.get('title', '')
                album, artist = parse_title_artist(title)
                
                # Get URL
                link = entry.get('link', '')
                
                # Get excerpt/summary
                excerpt = ""
                if hasattr(entry, 'summary'):
                    excerpt = entry.summary
                elif hasattr(entry, 'description'):
                    excerpt = entry.description
                # Clean HTML from excerpt
                excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()
                excerpt = excerpt[:500] if len(excerpt) > 500 else excerpt
                
                review = {
                    "album": album,
                    "artist": artist,
                    "score": None,
                    "url": link,
                    "source": site_id,
                    "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else None,
                    "tags": SITES[site_id]["tags"],
                    "excerpt": excerpt,
                    "site_id": site_id,
                    "crawl_status": "success"
                }
                reviews.append(review)
            except Exception as e:
                print(f"  Error parsing entry: {e}")
                continue
                
    except Exception as e:
        print(f"  Error scraping {site_id} with curl: {e}")
    
    return reviews

def parse_title_artist(title):
    """Parse album and artist from a title string"""
    if not title:
        return "", ""
    
    # Common patterns: "Album - Artist", "Artist: Album", "Album by Artist"
    patterns = [
        r'^(.+?)\s*-\s*(.+)$',  # "Album - Artist"
        r'^(.+?)\s*:\s*(.+)$',  # "Artist: Album" or "Album: Artist"
        r'^(.+?)\s+by\s+(.+)$', # "Album by Artist"
        r'^(.+?)\s*\|\s*(.+)$', # "Album | Artist"
    ]
    
    for pattern in patterns:
        m = re.match(pattern, title.strip())
        if m:
            g1, g2 = m.groups()
            # Try to determine which is album vs artist
            if 'review' in g1.lower() or 'review' in g2.lower():
                continue
            # Assume first is album, second is artist
            return g1.strip(), g2.strip()
    
    # If no pattern matches, return title as album
    return title.strip(), ""

def main():
    print(f"Starting scraper batch for 2026-05-14")
    print(f"Date range: {DATE_FROM.strftime('%Y-%m-%d')} to {DATE_TO.strftime('%Y-%m-%d')}")
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    
    total_reviews = 0
    
    for site_id, config in SITES.items():
        print(f"Scraping {config['name']} ({site_id})...")
        
        if config["strategy"] == "http_get":
            reviews = scrape_with_curl(
                site_id, 
                config["url"],
                config.get("rss_url")
            )
        else:
            # For playwright_headless, we'll just output empty array
            # and let the browser_navigate calls handle these
            print(f"  -> Skipping {site_id} (requires browser_navigate)")
            reviews = []
        
        count = write_output(site_id, reviews)
        total_reviews += count
    
    print(f"\nTotal reviews scraped: {total_reviews}")

if __name__ == "__main__":
    main()
