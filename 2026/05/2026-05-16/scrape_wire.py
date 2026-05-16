import urllib.request
import re
from datetime import datetime, timedelta

# Check if there's a reviews listing page
for url in [
    'https://www.thewire.co.uk/in-writing/reviews',
    'https://www.thewire.co.uk/reviews',
    'https://www.thewire.co.uk/in-writing/columns',
]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode('utf-8', errors='replace')
        h2s = re.findall(r'<h2>([^<]+)</h2>', html)
        may_refs = re.findall(r'2026/05/', html)
        print(f"\n{url}")
        print(f"  Status: {resp.status}, May refs: {len(may_refs)}")
        print(f"  H2s: {h2s[:5]}")
        if may_refs:
            # find first May context
            idx = html.find('2026/05/')
            print(f"  First May context: {html[max(0,idx-100):idx+100]}")
    except Exception as e:
        print(f"\n{url}: ERROR {e}")
