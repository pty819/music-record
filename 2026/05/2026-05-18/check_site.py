import urllib.request
import re
import json

url = 'https://rootsworld.com/rw/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print('Status:', resp.status)
    content = resp.read().decode('utf-8', errors='replace')
    print('Length:', len(content))
    # Look for review links
    links = re.findall(r'href=["\']([^"\']+)["\'][^>]*>([^<]*review[^<]*)', content, re.IGNORECASE)
    print('Review links:', links[:10])
    # Look for article links
    article_links = re.findall(r'href=["\']([^"\']+/[^/\s]+)["\']', content)
    print('All links sample:', article_links[:20])
except Exception as e:
    print('Error:', e)