import json, re, datetime, html
from urllib.parse import urljoin

# Try to get the listing page and find review links
import urllib.request

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml',
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return f"ERROR: {e}"

# Try homepage first
html_content = fetch('https://www.hhv-mag.com/')
print(f"Homepage length: {len(html_content)}")
print(html_content[:500])
