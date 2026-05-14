import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return resp.read().decode('utf-8', errors='replace')

# Get the reviews page HTML
url = 'https://www.squidco.com/ear/earReviews.shtml'
html = fetch(url)

# Look for sort/order settings
patterns = [
    r'resetOrder\("([^"]+)"\)',
    r'orderBy\s*=\s*"([^"]+)"',
    r'sort\s*=\s*"([^"]+)"',
    r'cookie.*?=.*?"([^"]+)"',
    r'squidEarReviewSort\s*=\s*"([^"]+)"',
    r'squidEarReviewFilter\s*=\s*"([^"]+)"',
]
print('Looking for sort/order settings:')
for pat in patterns:
    m = re.search(pat, html)
    if m:
        print(f'  {pat}: {m.group(0)}')

# Also look for the JavaScript that sets initial sort
print('\nSearching for updateTable call:')
m = re.search(r'updateTable\(([^)]*)\)', html)
if m:
    print(f'  updateTable call: {m.group(0)}')

# Look for any hidden fields or initial values
print('\nSearching for hidden inputs or initial values:')
hidden = re.findall(r'<input[^>]+value="([^"]+)"[^>]*>', html)
print('  Input values:', hidden[:10])

# Check if there's a specific API endpoint pattern
print('\nSearching for any date-related content:')
date_mentions = re.findall(r'.{0,30}(date|order|sort|recent|new).{0,30}', html, re.IGNORECASE)
for d in date_mentions[:10]:
    print(f'  {d.strip()}')
