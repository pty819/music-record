import urllib.request
import feedparser
from datetime import datetime, timedelta

# Check RSS feed
url = 'https://www.truthandliesmusic.com/feed/'
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        content = resp.read().decode('utf-8', errors='replace')
    print('RSS status:', resp.status)
    print('Content length:', len(content))
    print('First 800 chars:', content[:800])
except Exception as e:
    print('RSS Error:', e)

print("\n--- Checking main site ---")
try:
    with urllib.request.urlopen('https://www.truthandliesmusic.com/', timeout=10) as resp:
        main_content = resp.read().decode('utf-8', errors='replace')
    print('Main site status:', resp.status)
    print('Title tag:', main_content[main_content.find('<title>'):main_content.find('</title>')+8] if '<title>' in main_content else 'No title')
except Exception as e:
    print('Main site error:', e)