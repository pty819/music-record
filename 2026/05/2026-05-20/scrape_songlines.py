#!/usr/bin/env python3
"""Scrape Songlines reviews/features via browser (Camoufox)."""

import json
import re
import sys
from datetime import datetime, timedelta

# Today's date
TODAY = datetime(2026, 5, 20)
THREE_DAYS_AGO = TODAY - timedelta(days=3)
print(f"Today: {TODAY.date()}, 3 days ago: {THREE_DAYS_AGO.date()}", file=sys.stderr)

results = []
site_id = "songlines"
source_base = "https://www.songlines.co.uk"

def parse_star_rating(text):
    """Extract score from star rating text like 'Rating: ★★★★★★★★'."""
    if not text:
        return None
    matches = re.findall(r'★', text)
    if matches:
        return len(matches)
    return None

def strip_html(text):
    """Remove HTML tags from text."""
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def parse_features_date(date_str):
    """Parse date like 'MONDAY, MAY 18, 2026' or 'THURSDAY, MAY 14, 2026'."""
    date_str = date_str.strip()
    try:
        return datetime.strptime(date_str.upper(), "%A, %B %d, %Y")
    except ValueError:
        try:
            return datetime.strptime(date_str.upper(), "%B %d, %Y")
        except ValueError:
            return None

def is_within_3_days(dt):
    """Check if date is within 3 days of today."""
    if dt is None:
        return False
    return THREE_DAYS_AGO <= dt <= TODAY

def get_text_between(root, before, after=""):
    """Simple text extraction between markers."""
    pattern = re.escape(before) + r'(.*?)' + (re.escape(after) if after else r'$')
    m = re.search(pattern, root, re.DOTALL)
    return m.group(1).strip() if m else ""

# ─── STEP 1: Scrape Features pages ───────────────────────────────────────────

features_url = f"{source_base}/features"
print(f"Scraping features: {features_url}", file=sys.stderr)

# We'll use browser for features since it has specific dates
import subprocess

# Features page 1 - get articles with dates
cmd = [
    'python3', '-c', '''
import urllib.request
import re
import json
from datetime import datetime

url = "https://www.songlines.co.uk/features"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=15) as r:
    html = r.read().decode("utf-8", errors="replace")

# Find all article entries with their dates
# Pattern: DATE then TITLE
# Dates look like: MONDAY, MAY 18, 2026 or THURSDAY, MAY 14, 2026
pattern = r'<a href="(/feature/[^"]+)"[^>]*>\s*([^<]+)\s*</a>.*?<span class="field-date">([^<]+)</span>'

# Alternative: split by article blocks
# Each article has date and title

articles = []
# Find date+title pairs
date_pattern = r'([A-Z]{3,10},?\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})'
link_pattern = r'<a href="(/feature/[^"]+)">([^<]+)</a>'

# Split HTML into blocks
blocks = re.split(r'<div class="views-row[^"]*"', html)
for block in blocks[1:]:
    # Extract date
    date_m = re.search(r'([A-Z][a-z]+day,?\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})', block)
    if not date_m:
        date_m = re.search(r'(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})', block)
    
    # Extract link and title
    link_m = re.search(r'<a href="(/feature/[^"?#]+)"[^>]*>\s*<strong>\s*([^<]+)', block)
    if not link_m:
        link_m = re.search(r'<a href="(/feature/[^"?#]+)"[^>]*>([^<]+)</a>', block)
    
    if link_m:
        href = link_m.group(1)
        title = link_m.group(2).strip()
        date_str = date_m.group(1).strip() if date_m else ""
        
        try:
            dt = datetime.strptime(date_str.upper().replace(',', ''), "%A %B %d %Y")
        except:
            try:
                dt = datetime.strptime(date_str.upper().replace(',', ''), "%B %d %Y")
            except:
                dt = None
        
        articles.append({
            "url": "https://www.songlines.co.uk" + href,
            "title": title,
            "date": date_str,
            "dt": dt.isoformat() if dt else None
        })

print(json.dumps(articles[:20]))
'''
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
print(f"Features extraction stdout: {result.stdout[:500]}", file=sys.stderr)
if result.stderr:
    print(f"Features extraction stderr: {result.stderr[:200]}", file=sys.stderr)
