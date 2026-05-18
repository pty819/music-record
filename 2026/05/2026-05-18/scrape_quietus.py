#!/usr/bin/env python3
"""
Scrape The Quietus album reviews using browser automation.
Only collects articles within the last 3 days (May 15-18, 2026).
"""
import json
import re
from datetime import datetime

# Cutoff: articles published on or after this date
CUTOFF_DATE = datetime(2026, 5, 15)
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-18/the_quietus_reviews.json"
TAGS = ["experimental", "electronic", "jazz", "world", "psych", "prog", "free-improv"]
SITE_ID = "the_quietus"

def parse_date(date_str):
    """Parse date like 'Published 6:00am 15 May 2026'"""
    m = re.search(r'(\d+)\s+(\w+)\s+(\d{4})', date_str)
    if not m:
        return None
    day, month_str, year = int(m.group(1)), m.group(2), int(m.group(3))
    month_map = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,
                 'July':7,'August':8,'September':9,'October':10,'November':11,'December':12}
    try:
        return datetime(year, month_map[month_str], day)
    except:
        return None

def is_music_review(album, artist):
    """Filter out DVD/Blu-ray/TV reviews"""
    non_music = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD']
    text = (album + ' ' + artist).upper()
    return not any(kw in text for kw in non_music)

def make_entry(artist, album, score, url, pub_date_str, excerpt, review_type="review"):
    pub_date = parse_date(pub_date_str)
    if not pub_date or pub_date < CUTOFF_DATE:
        return None
    if not is_music_review(album, artist):
        return None
    
    return {
        "album": album.strip(),
        "artist": artist.strip(),
        "score": score,
        "url": url,
        "source": "The Quietus",
        "pub_date": pub_date.strftime('%Y-%m-%d'),
        "tags": TAGS,
        "excerpt": excerpt[:500].strip() if excerpt else "",
        "site_id": SITE_ID,
        "crawl_status": "scraped",
        "type": review_type
    }

# All review URLs from the listing page
# These are from page 1 and were all published May 15-18 (within 3-day window)
review_urls = [
    "https://thequietus.com/quietus-reviews/speedy-j-walkman-review/",
    "https://thequietus.com/quietus-reviews/darkthrone-pre-historic-metal-review/",
    "https://thequietus.com/quietus-reviews/sergeant-symbols-review/",
    "https://thequietus.com/quietus-reviews/laurie-anderson-with-sexmob-let-xx-live-review/",
    "https://thequietus.com/quietus-reviews/loraine-james-detached-from-the-rest-of-you-review/",
    "https://thequietus.com/quietus-reviews/max-cooper-feeling-is-structure/",
    "https://thequietus.com/quietus-reviews/octo-octa-sigils-for-survival-review/",
    "https://thequietus.com/quietus-reviews/russel-haswell-let-it-go-review/",
    "https://thequietus.com/quietus-reviews/irked-the-grievance-review/",
    "https://thequietus.com/quietus-reviews/lucy-liyou-mr-cobra-review/",
    "https://thequietus.com/quietus-reviews/bonner-kramer-thurston-moore-they-came-like-swallows-review/",
    "https://thequietus.com/quietus-reviews/aja-ireland-moult-mouth-review/",
    "https://thequietus.com/quietus-reviews/quentin-tolimieri-monochromes-ii-review/",
    "https://thequietus.com/quietus-reviews/carla-dal-forno-confession-review/",
    "https://thequietus.com/quietus-reviews/irmin-schmidt-requiem-review/",
    "https://thequietus.com/quietus-reviews/quiet-light-blue-angel-sparkling-silver-angel-2-review/",
    "https://thequietus.com/quietus-reviews/bali-gamelan-sound-topeng-semar-pegulingan-review/",
    "https://thequietus.com/quietus-reviews/tanya-donelly-and-chris-brokaw-the-undone-is-done-again-review/",
    "https://thequietus.com/quietus-reviews/gnod-chronicles-of-gnowt-vol-1-review/",
    "https://thequietus.com/quietus-reviews/nine-inch-noize-nine-inch-noize-nine-inch-nails-review/",
    "https://thequietus.com/quietus-reviews/graham-dunning-quern-review/",
    "https://thequietus.com/quietus-reviews/nana-rizinni-epiblast-review/",
    "https://thequietus.com/quietus-reviews/abigail-snail-rad-berms-review/",
    "https://thequietus.com/quietus-reviews/adult-kissing-luck-goodbye-review/",
    "https://thequietus.com/quietus-reviews/drass-on-the-hill-review/",
    "https://thequietus.com/quietus-reviews/radwan-ghazi-moumneh-frederic-d-oberland-review/",
    "https://thequietus.com/quietus-reviews/my-new-band-believe-my-new-band-believe-review/",
    "https://thequietus.com/quietus-reviews/squarepusher-kammerkonzert-review/",
    "https://thequietus.com/quietus-reviews/melvins-napalm-death-savage-imperial-death-march-review/",
    "https://thequietus.com/quietus-reviews/memorials-all-clouds-bring-not-rain-review/",
    "https://thequietus.com/quietus-reviews/wendy-eisenberg-wendy-eisenberg-review/",
    "https://thequietus.com/quietus-reviews/mclusky-i-sure-am-getting-sick-of-this-bowling-alley-review/",
    "https://thequietus.com/quietus-reviews/mr-vast-upping-the-ante-review/",
]

print(f"Total review URLs: {len(review_urls)}")
print("This script should be run via browser_navigate + browser_console calls,")
print("not standalone. See scrape_workflow below.")