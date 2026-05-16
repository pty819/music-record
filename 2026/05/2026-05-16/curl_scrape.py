#!/usr/bin/env python3
"""Scrape Wild City articles."""

import subprocess
import re
import json
import ssl
import time
from datetime import datetime

BASE = "https://www.thewildcity.com"
CUTOFF = datetime(2026, 5, 13)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def curl_get(url):
    """Use subprocess to run curl."""
    result = subprocess.run(
        ['curl', '-s', '-L', '--max-time', '20', '-A', 'Mozilla/5.0', '--tlsv1.2', url],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout

def parse_date(s):
    m = re.match(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s.strip())
    if m:
        mo = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}.get(m.group(2).lower()[:3], 0)
        if mo:
            return datetime(int(m.group(3)), mo, int(m.group(1)))
    return None

# Fetch homepage
print("Fetching homepage...")
html = curl_get(BASE + "/")
print(f"Homepage length: {len(html)}")

# Find all article links
links = re.findall(r'href="(https://www\.thewildcity\.com/[^"]+)"', html)
seen = set()
news_links = []
feature_links = []
mix_links = []

for link in links:
    if link in seen:
        continue
    seen.add(link)
    if '/news/' in link and '/author/' not in link and '/tag/' not in link and '/page/' not in link:
        news_links.append(link)
    elif '/features/' in link and '/author/' not in link and '/tag/' not in link and '/page/' not in link:
        feature_links.append(link)
    elif '/mixes/' in link and '/author/' not in link and '/tag/' not in link and '/page/' not in link:
        mix_links.append(link)

print(f"News links: {len(news_links)}")
print(f"Feature links: {len(feature_links)}")
print(f"Mix links: {len(mix_links)}")

for l in news_links[:15]:
    print(f"  {l}")
print("---")
for l in feature_links[:5]:
    print(f"  {l}")
print("---")
for l in mix_links[:5]:
    print(f"  {l}")