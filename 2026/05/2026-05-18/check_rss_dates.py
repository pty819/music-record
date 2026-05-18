#!/usr/bin/env python3
import feedparser
import json
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# Parse the RSS
feed = feedparser.parse('/home/liyifan/music-record/2026/05/2026-05-18/rss_output.xml')

print(f'Feed title: {feed.feed.get("title", "")}')
print(f'Number of entries: {len(feed.entries)}')

# Calculate 3-day cutoff
now = datetime.now()
cutoff = now - timedelta(days=3)
print(f'\nCutoff date (3 days ago): {cutoff.strftime("%Y-%m-%d")}')
print(f'Current date: {now.strftime("%Y-%m-%d")}')

# Check dates of all entries
all_dates = []
for entry in feed.entries:
    pub_str = entry.get('published') or entry.get('updated') or ''
    try:
        pub_date = parsedate_to_datetime(pub_str)
        # Make cutoff timezone-aware if pub_date is aware
        if pub_date.tzinfo is not None:
            cutoff_aware = cutoff.replace(tzinfo=pub_date.tzinfo)
        else:
            cutoff_aware = cutoff
        all_dates.append((pub_date, cutoff_aware, entry.get('title', '')[:50], entry.get('link', '')))
    except Exception as e:
        print(f'Could not parse date: {pub_str} - {e}')

if all_dates:
    all_dates.sort(key=lambda x: x[0])
    print(f'\nOldest entry: {all_dates[0][0].strftime("%Y-%m-%d")}')
    print(f'Newest entry: {all_dates[-1][0].strftime("%Y-%m-%d")}')

print('\n--- Entries within 3 days ---')
recent_count = 0
for pub_date, cutoff_aware, title, link in all_dates:
    if pub_date >= cutoff_aware:
        print(f'{pub_date.strftime("%Y-%m-%d")} - {title}')
        print(f'  {link}')
        recent_count += 1

print(f'\nTotal recent: {recent_count}')

print('\n--- 5 most recent entries ---')
for pub_date, _, title, link in all_dates[-5:]:
    print(f'{pub_date.strftime("%Y-%m-%d")} - {title}')