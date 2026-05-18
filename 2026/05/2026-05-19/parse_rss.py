#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

content = sys.stdin.read()
root = ET.fromstring(content)
channel = root.find('channel')
items = channel.findall('item')
print(f'Total items: {len(items)}')
now = datetime.now(timezone.utc)

for item in items:
    title_el = item.find('title')
    link_el = item.find('link')
    pub_el = item.find('pubDate')
    if title_el is None or link_el is None or pub_el is None:
        continue
    title = title_el.text or ''
    link = link_el.text or ''
    pub_date_str = pub_el.text or ''
    try:
        pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
        age = (now - pub_date).days
    except:
        pub_date = None
        age = 'N/A'
    print(f'  {pub_date_str} ({age}d ago) - {title[:80]}')
    print(f'    {link}')
