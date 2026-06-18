#!/usr/bin/env python3
"""Debug ProgressoR review page parsing."""
import urllib.request
import re
from datetime import datetime, timezone

# Copy the exact regexes from the scraper
REVIEW_HEADER_RE = re.compile(
    r"^\s*(?P<artist>[^-]+?)\s*-\s*"
    r"(?P<year>\d{4})\s*-\s*"
    r"(?P<quote>[\"\u201c\u201d'`])?(?P<album>.+?)(?P=quote)\s*$",
    re.U,
)
PUBTAG_RE = re.compile(
    r"Prog(?:tector|messor):\s*(?P<month>January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+(?P<year>\d{4})",
    re.I,
)
LABEL_LINE_RE = re.compile(r"\((?P<runtime>[\d:]+)\s*;\s*(?P<label>[^)]+)\)")

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# Fetch a review page
url = 'http://www.progressor.net/review/gong_2026.html'
with urllib.request.urlopen(url, timeout=15) as resp:
    html = resp.read().decode('utf-8', errors='replace')

# Strip HTML (same as scraper does)
text = re.sub(r'<[^>]+>', ' ', html)
text = re.sub(r'\s+', ' ', text).strip()

lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
print(f"=== Lines ({len(lines)} total) ===")
for i, ln in enumerate(lines[:30]):
    print(f"  {i}: |{ln}|")
    
print("\n=== Regex tests ===")
for ln in lines[:15]:
    m = REVIEW_HEADER_RE.match(ln)
    if m:
        print(f"  HEADER MATCH: artist={m.group('artist')!r}, album={m.group('album')!r}, year={m.group('year')!r}")
    m2 = LABEL_LINE_RE.match(ln)
    if m2:
        print(f"  LABEL MATCH: runtime={m2.group('runtime')!r}, label={m2.group('label')!r}")
    m3 = PUBTAG_RE.search(ln)
    if m3:
        print(f"  PUBTAG MATCH: month={m3.group('month')!r}, year={m3.group('year')!r}")
