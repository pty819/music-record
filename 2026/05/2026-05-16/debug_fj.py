import re, html, feedparser

d = feedparser.parse('https://avantmusicnews.com/feed/')
for e in d.entries:
    if 'Free Jazz' in e.get('title',''):
        raw = e.get('summary_detail',{}).get('value','') or e.get('summary','')
        raw = html.unescape(raw)
        print("=== Free Jazz Collective raw ===")
        print(repr(raw[:600]))
        print()
        
        # Test REVIEW_PAT1
        REVIEW_PAT1 = re.compile(
            r"([A-Z][a-z]+ \d{1,2}, \d{4})"
            r"\s*[—–-]\s*"
            r"([^,]+)\s*,\s*"
            r"[\"\u201c\u201d\u2018\u2019]([^\"\u201c\u201d\u2018\u2019]+)[\"\u201c\u201d\u2018\u2019]"
            r"\s*\(([^)]+)\)"
            r"(?:\s*reviewed by ([^.]+))?",
            re.IGNORECASE
        )
        print("PAT1 matches:", list(REVIEW_PAT1.finditer(raw)))
        
        # Test free jazz pattern
        FREE_JAZZ_PAT = re.compile(r'\.\s*reviewed by\s*', re.IGNORECASE)
        print("FREE_JAZZ matches:", list(FREE_JAZZ_PAT.finditer(raw)))
        break
