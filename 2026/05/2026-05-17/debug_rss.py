#!/usr/bin/env python3
import subprocess, re

def get_page_via_curl(url):
    result = subprocess.run([
        'curl', '-s', '--max-time', '20', '-L', '-A',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        url
    ], capture_output=True, text=True)
    return result.stdout

# The correct RSS URL from the page source
rss_text = get_page_via_curl('https://thequietus.com/quietus-reviews/rss')
print(f"Length: {len(rss_text)}")
print("First 1000 chars:")
print(rss_text[:1000])
print("\n---\nLooking for item tags:")
print("Has <item>:", '<item>' in rss_text)
print("Has <entry>:", '<entry>' in rss_text)
# Look for what tag might be used
tag_matches = re.findall(r'<(\w+)\s', rss_text[:2000])
unique_tags = set(tag_matches)
print("Tags found:", sorted(unique_tags)[:30])