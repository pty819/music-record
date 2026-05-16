#!/usr/bin/env python3
"""Parse fRoots RSS and check dates."""

import urllib.request
import feedparser
from datetime import datetime, timedelta

base = 'https://frootsmag.com'
headers = {'User-Agent': 'Mozilla/5.0'}
cutoff = datetime.now() - timedelta(days=3)
cutoff_ts = cutoff.timestamp()
print(f"Cutoff: {cutoff} ({cutoff_ts})")

url = base + '/feed/'
req = urllib.request.Request(url, headers=headers)
resp = urllib.request.urlopen(req, timeout=10)
content = resp.read().decode('utf-8', errors='replace')

feed = feedparser.parse(content)
print(f"Entries: {len(feed.entries)}")
print(f"LastBuildDate: {feed.feed.get('lastbuilddate', 'N/A')}")

now_ts = datetime.now().timestamp()
for i, e in enumerate(feed.entries[:20]):
    pub = e.get('published', e.get('updated', 'N/A'))
    pub_parsed = e.get('published_parsed')
    if pub_parsed:
        pub_ts = datetime(*pub_parsed[:6]).timestamp()
        age_days = (now_ts - pub_ts) / 86400
        in_range = pub_ts >= cutoff_ts
        print(f"{i+1}. {pub} | age={age_days:.1f}d | in_range={in_range} | title={e.title[:60]}")
    else:
        print(f"{i+1}. no date | title={e.title[:60]}")
    # Check description/summary
    desc = e.get('description', '')[:100]
    summary = e.get('summary', '')[:100]
    print(f"   desc={desc}")
    print(f"   summary={summary}")