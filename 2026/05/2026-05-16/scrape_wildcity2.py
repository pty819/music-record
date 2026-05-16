#!/usr/bin/env python3
import urllib.request
import re
import ssl
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE = "https://www.thewildcity.com"

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error {url}: {e}")
        return None

# Get news page to find all article links
html = get(BASE + "/news")
if not html:
    print("Failed to fetch homepage")
    exit(1)

# Find all thewildcity.com links
links = re.findall(r'href="(https://www\.thewildcity\.com/[^"]+)"', html)
seen = set()
news_links = []
feature_links = []
mix_links = []

for link in links:
    if link in seen:
        continue
    seen.add(link)
    if '/news/' in link and '/author/' not in link and '/tag/' not in link:
        news_links.append(link)
    elif '/features/' in link and '/author/' not in link and '/tag/' not in link:
        feature_links.append(link)
    elif '/mixes/' in link and '/author/' not in link and '/tag/' not in link:
        mix_links.append(link)

print(f"News links: {len(news_links)}")
for l in news_links[:10]:
    print(f"  {l}")

print(f"\nFeature links: {len(feature_links)}")
for l in feature_links[:10]:
    print(f"  {l}")

print(f"\nMix links: {len(mix_links)}")
for l in mix_links[:10]:
    print(f"  {l}")

# Now check dates for news + features
all_article_links = news_links[:10] + feature_links[:5]
print(f"\nChecking dates for {len(all_article_links)} articles...")

def parse_date(s):
    m = re.match(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s.strip())
    if m:
        mo = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}.get(m.group(2).lower()[:3], 0)
        if mo:
            return __import__('datetime').datetime(int(m.group(3)), mo, int(m.group(1)))
    return None

cutoff = __import__('datetime').datetime(2026, 5, 13)
results = []

for url in all_article_links:
    print(f"\n  Fetching: {url}")
    article_html = get(url)
    if not article_html:
        continue
    time.sleep(0.5)

    # Get date
    date_m = re.search(r'<em[^>]*>\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*</em>', article_html)
    pub_date = None
    if date_m:
        pub_date = parse_date(date_m.group(1))
        print(f"    Date: {date_m.group(1)} -> {pub_date}")
    else:
        print(f"    No date found in <em>")

    # Get title
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', article_html, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ''

    # Skip if outside cutoff
    if pub_date and pub_date < cutoff:
        print(f"    >>> OUTSIDE window (before May 13)")
        continue

    print(f"    >>> WITHIN window")
    results.append((url, pub_date, title))

print(f"\n\nTotal within window: {len(results)}")
for r in results:
    print(f"  {r[1]} - {r[2][:60]} - {r[0]}")