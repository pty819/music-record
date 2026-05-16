import feedparser
import ssl
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# Check RSS
url = 'https://www.modernclassicalmusic.com/feed'
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

d = feedparser.parse(url)
print('All entries:')
cutoff = datetime.utcnow() - timedelta(days=3)
print('Cutoff:', cutoff)
for e in d.entries:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if pub:
        dt = datetime(*pub[:6])
    else:
        dt = None
    print('-', e.get('title',''), '|', e.get('published',''), '| dt:', dt, '| within 3 days:', dt >= cutoff if dt else 'N/A')