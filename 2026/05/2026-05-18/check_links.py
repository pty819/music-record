import urllib.request
import re

req = urllib.request.Request('https://thequietus.com/columns/quietus-reviews/', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=15) as r:
    html = r.read().decode('utf-8', errors='replace')

links = re.findall(r'href="(/[^"]+)"', html)
for l in links:
    if 'review' in l.lower() or 'quietus-reviews' in l.lower():
        print(repr(l))