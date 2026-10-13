#!/usr/bin/env python3
"""Debug: fetch and show a ProgressoR review page."""
import urllib.request
import re

url = 'http://www.progressor.net/review/gong_2026.html'
try:
    with urllib.request.urlopen(url, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='replace')
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    print(text[:3000])
except Exception as e:
    print(f'Error: {e}')
