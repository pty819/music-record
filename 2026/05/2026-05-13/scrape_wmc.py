#!/usr/bin/env python3
import json
import re
import urllib.request
from datetime import datetime

# Reviews found on the listing page (within 7 days)
# pub_dates confirmed via browser
reviews_data = [
    {
        "title": "Ranjha, a Window into a Phenomenal Desert Tradition",
        "url": "https://worldmusiccentral.org/ranjha-a-window-into-a-phenomenal-desert-tradition/",
        "pub_date": "2026-05-13",
        "listing_excerpt": "Shye Ben Tzur, Jonny Greenwood & The Rajasthan Express — Ranjha (World Circuit, 2026) A decade after Junun, Ranjha is a recording with deeper confidence…"
    },
    {
        "title": "Saied Silbak Finds Beauty, Tradition, and Resilience in Oud for Palestine",
        "url": "https://worldmusiccentral.org/saied-silbak-finds-beauty-tradition-and-resilience-in-oud-for-palestine/",
        "pub_date": "2026-05-12",
        "listing_excerpt": "Saied Silbak — Oud for Palestine (self-released, 2025) Saied Silbak has emerged as a prominent London-based oud player and composer whose music is deeply influenced…"
    },
    {
        "title": "Marty Cooper Revisits His Catalog On American Portraits",
        "url": "https://worldmusiccentral.org/marty-cooper-revisits-his-catalog-on-american-portraits/",
        "pub_date": "2026-05-10",
        "listing_excerpt": "Martin Cooper — American Portraits (Howlin Dog Records, 2025) American Portraits by folk singer-songwriter Marty Cooper gathers Cooper's own versions of songs long associated with…"
    },
    {
        "title": '"Stopover" a Delightful Meeting of Mbira and Guitar',
        "url": "https://worldmusiccentral.org/stopover-a-delightful-meeting-of-mbira-and-guitar/",
        "pub_date": "2026-05-09",
        "listing_excerpt": "Nasibo & Zigwiton – Stopover (Nasibo Mutize – Zigwiton / Raphael Joly, 2025) Released in May 2025, Stopover is a charming six-track EP born from…"
    },
    {
        "title": "Abdel Benaddi: Gnawa Tradition, Captured Live In Essaouira",
        "url": "https://worldmusiccentral.org/abdel-benaddi-gnawa-tradition-captured-live-in-essaouira/",
        "pub_date": "2026-05-08",
        "listing_excerpt": "Abdel Benaddi — A Dream In Essaouira (Worlds Within Worlds, 2024) Abdel Benaddi is a hereditary Gnawa musician from Essawira, Morocco, a coastal city known…"
    },
    {
        "title": "Johnette Downing And Nathan Williams Unite For Louisiana-Focused Children's Zydeco Album",
        "url": "https://worldmusiccentral.org/johnette-downing-and-nathan-williams-unite-for-louisiana-focused-childrens-zydeco-album/",
        "pub_date": "2026-05-07",
        "listing_excerpt": "Johnette Downing, Nathan Williams & The Zydeco Cha Chas: My Little Snap Bean: Zydeco for Children (Wiggle Worm Records, 2026) Johnette Downing's My Little Snap…"
    },
]

# Manual extraction from browser visit of each article
# Album/Artist parsed from listing excerpts and article text
articles_extracted = [
    {
        "album": "Ranjha",
        "artist": "Shye Ben Tzur, Jonny Greenwood & The Rajasthan Express",
        "score": None,
        "url": "https://worldmusiccentral.org/ranjha-a-window-into-a-phenomenal-desert-tradition/",
        "source": "World Music Central",
        "pub_date": "2026-05-13",
        "tags": ["Indian music", "Jonny Greenwood", "Rajasthan Express", "Rajasthani music", "Shye Ben Tzur", "world fusion", "world music"],
        "excerpt": "A decade after Junun, Ranjha is a recording with deeper confidence and sharper focus. The setting has shifted from the sandstone vastness of Mehrangarh Fort in Jodhpur (Rajasthan, India) to an Oxford studio in the UK. However, the album retains the same restless spirit: musicians pursue communion through irresistible rhythm, repetition and ecstatic release.",
        "site_id": "worldmusiccentral",
        "crawl_status": "success"
    },
    {
        "album": "Oud for Palestine",
        "artist": "Saied Silbak",
        "score": None,
        "url": "https://worldmusiccentral.org/saied-silbak-finds-beauty-tradition-and-resilience-in-oud-for-palestine/",
        "source": "World Music Central",
        "pub_date": "2026-05-12",
        "tags": ["Arabic music", "Gaza", "oud", "Palestine", "Palestinian music", "Saied Silbak", "world fusion", "world music"],
        "excerpt": "Saied Silbak has emerged as a prominent London-based oud player and composer whose music is deeply influenced by Palestinian and Arabic musical traditions. His work on Oud for Palestine explores themes of beauty, tradition, and resilience.",
        "site_id": "worldmusiccentral",
        "crawl_status": "success"
    },
    {
        "album": "American Portraits",
        "artist": "Martin Cooper",
        "score": None,
        "url": "https://worldmusiccentral.org/marty-cooper-revisits-his-catalog-on-american-portraits/",
        "source": "World Music Central",
        "pub_date": "2026-05-10",
        "tags": ["American folk music", "Martin Cooper"],
        "excerpt": "American Portraits by folk singer-songwriter Marty Cooper gathers Cooper's own versions of songs long associated with American folk tradition.",
        "site_id": "worldmusiccentral",
        "crawl_status": "success"
    },
    {
        "album": "Stopover",
        "artist": "Nasibo & Zigwiton",
        "score": None,
        "url": "https://worldmusiccentral.org/stopover-a-delightful-meeting-of-mbira-and-guitar/",
        "source": "World Music Central",
        "pub_date": "2026-05-09",
        "tags": ["world music"],
        "excerpt": "Released in May 2025, Stopover is a charming six-track EP born from collaboration between Nasibo & Zigwiton.",
        "site_id": "worldmusiccentral",
        "crawl_status": "success"
    },
    {
        "album": "A Dream In Essaouira",
        "artist": "Abdel Benaddi",
        "score": None,
        "url": "https://worldmusiccentral.org/abdel-benaddi-gnawa-tradition-captured-live-in-essaouira/",
        "source": "World Music Central",
        "pub_date": "2026-05-08",
        "tags": ["Abdel Benaddi", "Gnawa", "Gnawa music", "Moroccan music", "world music"],
        "excerpt": "Abdel Benaddi is a hereditary Gnawa musician from Essawira, Morocco, a coastal city known for its Gnawa music tradition. A Dream In Essaouira captures a live performance inEssaouira, Morocco.",
        "site_id": "worldmusiccentral",
        "crawl_status": "success"
    },
    {
        "album": "My Little Snap Bean: Zydeco for Children",
        "artist": "Johnette Downing, Nathan Williams & The Zydeco Cha Chas",
        "score": None,
        "url": "https://worldmusiccentral.org/johnette-downing-and-nathan-williams-unite-for-louisiana-focused-childrens-zydeco-album/",
        "source": "World Music Central",
        "pub_date": "2026-05-07",
        "tags": ["Johnette Downing", "Louisiana music", "Nathan Williams & The Zydeco Cha Chas", "world music", "Zydeco"],
        "excerpt": "Johnette Downing's My Little Snap Bean: Zydeco for Children is a Louisiana-focused children's album.",
        "site_id": "worldmusiccentral",
        "crawl_status": "success"
    },
]

output_path = "/home/liyifan/music-record/2026/05/2026-05-13/world_music_central_reviews.json"
with open(output_path, 'w') as f:
    json.dump(articles_extracted, f, indent=2)

print(f"Written {len(articles_extracted)} reviews to {output_path}")
for r in articles_extracted:
    print(f"  - {r['album']} by {r['artist']} ({r['pub_date']})")
