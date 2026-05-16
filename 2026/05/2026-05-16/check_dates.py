import urllib.request
import re

# Check dates on magazine listing
url = 'https://www.truthandliesmusic.com/magazine/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as resp:
    content = resp.read().decode('utf-8', errors='replace')

# Look for all date patterns
dates = re.findall(r'(January|February|March|April|May|June|July|August|September|October|November|December) \d+, 2026', content)
print('All dates found on magazine page:', dates)

# Look for article links and their dates
article_dates = re.findall(r'/magazine/[^/]+/[^"]*".*?(January|February|March|April|May|June|July|August|September|October|November|December) \d+, 2026', content)
print('Article URLs with dates:', article_dates[:10])

# Check what's near May 13
idx = content.find('May 13')
if idx > 0:
    print('\nContext around May 13:')
    print(content[idx-100:idx+300])
else:
    print('May 13 not found directly in HTML')