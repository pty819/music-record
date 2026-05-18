#!/usr/bin/env python3
"""
Scrape I CARE IF YOU LISTEN - 3-day window filter
"""

import json
import re
from datetime import datetime, timezone

# Today's date in UTC (task spawned 2026-05-18 04:20 CST = 2026-05-17 20:20 UTC)
# The 3-day window means we want articles published on or after 2026-05-14 20:20 UTC
# But using a simple date comparison: articles on or after May 14

# For simplicity, let's treat May 15, 16, 17 as the 3-day window
# since the task was created on May 18 local time
# Using May 14 cutoff (3 full days prior to May 17 end)

from datetime import date
cutoff_date = date(2026, 5, 14)  # articles published on or after this date

print(f"Cutoff date: {cutoff_date}")
print()

# RSS feed data - items from earlier analysis
rss_items = [
    {
        "title": "The Ecstatic Experience of Dig That Treasure! Festival 2026",
        "link": "https://icareifyoulisten.com/2026/05/the-ecstatic-experience-of-dig-that-treasure-festival-2026/",
        "pubDate": "Thu, 14 May 2026 10:00:00 +0000",
        "category": "Concert",
        "author": "Robert Barry",
        "tags": ["Concert", "Abul Mogard", "Ailís Ní Ríain", "Cafe OTO", "Canab Marwo", "Dig That Treasure! Festival", "DNA? AND?", "Eric Chenaux", "Fievel Is Glauque", "Harry Górski-Brown", "IKLECTIK Art Lab", "Jennifer Walshe", "Lawrence Casserley", "Michelle Hromin", "Mohammad Syfkhan", "Rafael Anton Irisarri", "standard issue", "Tilly Coulton"],
        "type": "review",  # concert = review
    },
    {
        "title": "Malachi Brown and the Sounds of U.S.",
        "link": "https://icareifyoulisten.com/2026/05/malachi-brown-and-the-sounds-of-u-s/",
        "pubDate": "Wed, 13 May 2026 10:00:00 +0000",
        "category": "Interview",
        "author": "A. Kori Hill",
        "tags": ["Interview", "Alexander Davis", "Malachi Brown", "Recomposing America", "Sugar Hill Salon"],
        "type": "feature",  # interview = feature
    },
    {
        "title": "SydeBoob Duo's \"Au Naturel\" is a Bold and Athletic Debut",
        "link": "https://icareifyoulisten.com/2026/05/sydeboob-duo-au-naturel-is-a-bold-and-athletic-debut/",
        "pubDate": "Tue, 12 May 2026 10:00:00 +0000",
        "category": "Album",
        "author": "Tristan McKay",
        "tags": ["Album", "Anna Elder", "Anthony Braxton", "Beat Furrer", "Eric Moe", "Max Johnson", "Ramin Akhavijou", "Rebecca Saunders", "Sarah Steranka", "SydeBoob Duo"],
        "type": "review",  # album = review
    },
]

def parse_pub_date(pub_date_str):
    """Parse pub date from RSS format"""
    # Format: "Thu, 14 May 2026 10:00:00 +0000"
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(pub_date_str)
    except:
        return None

def in_3day_window(pub_date_str):
    dt = parse_pub_date(pub_date_str)
    if dt is None:
        return False
    # Using cutoff of May 14, 2026
    item_date = dt.date()
    return item_date >= cutoff_date

def strip_html(text):
    """Remove HTML tags from text"""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = clean.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
    clean = clean.replace('&#8216;', "'").replace('&#8217;', "'").replace('&#8230;', '...')
    clean = clean.replace('&#039;', "'")
    return clean.strip()

# Check RSS items
print("=== RSS Feed Items ===")
for item in rss_items:
    dt = parse_pub_date(item['pubDate'])
    in_window = in_3day_window(item['pubDate'])
    print(f"[{in_window}] {item['pubDate'][:16]} - {item['title'][:50]} - {item['category']}")
    if in_window:
        print(f"   EXCERPT: {item['description'][:100] if 'description' in item else 'N/A'}")

print(f"\nRSS items in 3-day window: {sum(1 for i in rss_items if in_3day_window(i['pubDate']))}")

# Now we need to visit each article to get:
# - Album/artist name (for album reviews)
# - Score (for reviews)
# - Full excerpt from description (CDATA has full content)

# First, let's get the full description from the RSS
import feedparser
feed = feedparser.parse("https://icareifyoulisten.com/feed")

print("\n=== Full RSS Content Check ===")
for e in feed.entries:
    pub = e.get('published', '')
    title = e.title
    # Check if in window
    if in_3day_window(pub):
        print(f"\nTitle: {title}")
        print(f"Link: {e.link}")
        print(f"Published: {pub}")
        print(f"Category: {[t.term for t in e.get('tags', [])][:3]}")
        # Get full content from summary
        summary = e.get('summary', '') or e.get('description', '')
        print(f"Summary (first 300 chars): {strip_html(summary)[:300]}")
        print(f"Author: {e.get('author', 'N/A')}")