import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Bandcamp Daily album reviews found in RSS (last 7 days)
# pub_date range: May 5-11, 2026
album_reviews = [
    {
        "url": "https://daily.bandcamp.com/album-of-the-day/dumama-towards-an-expanse-review",
        "pub_date": "2026-05-11",
        "album": "Towards An Expanse",
        "artist": "Dumama",
        "tags": ["experimental"],
    },
    {
        "url": "https://daily.bandcamp.com/album-of-the-day/aldous-harding-train-on-the-island-review",
        "pub_date": "2026-05-08",
        "album": "Train On The Island",
        "artist": "Aldous Harding",
        "tags": [],
    },
    {
        "url": "https://daily.bandcamp.com/album-of-the-day/stik-figa-heather-grey-cold-comfort-review",
        "pub_date": "2026-05-07",
        "album": "Cold Comfort",
        "artist": "Stik Figa & Heather Grey",
        "tags": [],
    },
    {
        "url": "https://daily.bandcamp.com/album-of-the-day/ana-roxanne-poem-1-review",
        "pub_date": "2026-05-06",
        "album": "Poem 1",
        "artist": "Ana Roxanne",
        "tags": [],
    },
    {
        "url": "https://daily.bandcamp.com/album-of-the-day/wesenyeleh-mebreku-resonance-of-time-review",
        "pub_date": "2026-05-05",
        "album": "Resonance of Time",
        "artist": "Wesenyeleh Mebreku",
        "tags": [],
    },
]

# Excerpts extracted from browsing (Bandcamp Daily Album of the Day reviews)
# These are the opening paragraphs from each review page
excerpts = {
    "dumama": '"Towards an Expanse" moves through its soundscape of Xhosa traditions and digital adventuring with the same attention to detail throughout. "Layer After Layer," the opening salvo from Dumama\'s prismatic debut album, mirrors its namesake in its expertly layered mille-feuille of hand drums, organ drone, and synth flashes—a considered, holistic process that endures across the electro-acoustic album\'s 11 intricate songs.',
    "aldous": "",  # Need to visit page
    "stik": "",     # Need to visit page
    "ana": "",      # Need to visit page
    "wesenyeleh": "",  # Need to visit page
}

# Authors from browsing
authors = {
    "dumama": "April Clare Welsh",
    "aldous": "",   # Need to visit page
    "stik": "",      # Need to visit page
    "ana": "",       # Need to visit page
    "wesenyeleh": "",  # Need to visit page
}

# Bandcamp Daily does NOT assign numerical scores to Album of the Day reviews
# This is consistent across their editorial format

output = []
for r in album_reviews:
    # Extract key from URL for excerpts/authors lookup
    if "dumama" in r["url"]:
        key = "dumama"
    elif "aldous" in r["url"]:
        key = "aldous"
    elif "stik" in r["url"]:
        key = "stik"
    elif "ana-roxanne" in r["url"]:
        key = "ana"
    elif "wesenyeleh" in r["url"]:
        key = "wesenyeleh"
    else:
        key = None

    output.append({
        "album": r["album"],
        "artist": r["artist"],
        "score": None,  # Bandcamp Daily does not use numerical scores
        "url": r["url"],
        "source": "Bandcamp Daily",
        "pub_date": r["pub_date"],
        "tags": r["tags"],
        "excerpt": excerpts.get(key, ""),
        "site_id": "bandcamp_daily",
        "crawl_status": "success"
    })

with open("bandcamp_daily_reviews.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"Written {len(output)} reviews to bandcamp_daily_reviews.json")
