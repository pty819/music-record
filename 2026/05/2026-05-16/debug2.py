#!/usr/bin/env python3
import feedparser
import re
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

ENTITIES = {
    '&#8216;': "'",
    '&#8217;': "'",
    '&#8220;': '"',
    '&#8221;': '"',
    '&#8230;': '…',
    '&#038;': '&',
    '&#160;': ' ',
    '&amp;': '&',
    '&nbsp;': ' ',
}

def clean_excerpt(raw_text):
    if not raw_text:
        return ""
    text = raw_text
    for entity, char in ENTITIES.items():
        text = text.replace(entity, char)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove "Continued The post X appeared first on..." cruft
    text = re.sub(r'\s*…?\s*Continued\s+The post.*?appeared first on.*?I CARE IF YOU LISTEN\.?\s*$',
                  '…', text, flags=re.IGNORECASE)
    text = text.strip()
    if len(text) > 500:
        text = text[:500].rsplit(' ', 1)[0] + '…'
    return text

feed = feedparser.parse("https://icareifyoulisten.com/feed")
entry = feed.entries[0]
raw = entry.get("summary_detail", {}).get("value", "") or entry.get("summary", "")
print("RAW first 300:", repr(raw[:300]))
print()
cleaned = clean_excerpt(raw)
print("CLEANED:", repr(cleaned[:300]))