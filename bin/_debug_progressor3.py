#!/usr/bin/env python3
"""Debug ProgressoR review page with BS4."""
import urllib.request
import re

url = 'http://www.progressor.net/review/gong_2026.html'
with urllib.request.urlopen(url, timeout=15) as resp:
    html = resp.read().decode('utf-8', errors='replace')

from bs4 import BeautifulSoup
soup = BeautifulSoup(html, "lxml")
text = soup.get_text(separator="\n", strip=True)

lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
print(f"=== {len(lines)} lines ===")
for i, ln in enumerate(lines[:20]):
    print(f"  {i}: |{ln[:100]}|")

# Test regexes
REVIEW_HEADER_RE = re.compile(
    r"^\s*(?P<artist>[^-]+?)\s*-\s*"
    r"(?P<year>\d{4})\s*-\s*"
    r"(?P<quote>[\"\u201c\u201d'`])?(?P<album>.+?)(?P=quote)\s*$",
    re.U,
)

print("\n=== Header regex tests ===")
for i, ln in enumerate(lines[:10]):
    m = REVIEW_HEADER_RE.match(ln)
    if m:
        print(f"  MATCH line {i}: artist={m.group('artist')!r} album={m.group('album')!r}")
    else:
        print(f"  NO match line {i}: |{ln[:80]}|")
