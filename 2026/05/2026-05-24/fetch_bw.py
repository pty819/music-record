#!/usr/bin/env python3
import subprocess, re, json

result = subprocess.run(
    ['curl', '-s', '--max-time', '20', '-L', 'https://www.bandwagon.asia/'],
    capture_output=True, text=True
)
html = result.stdout

links = re.findall(r'href="(https://www\.bandwagon\.asia/[^"]+)"', html)
unique = sorted(set(links))[:50]
for l in unique:
    print(l)

# Also look for article pattern in HTML
article_urls = [l for l in unique if re.search(r'/\d{4}/', l)]
print(f"\n--- Article URLs ({len(article_urls)}) ---")
for l in article_urls[:20]:
    print(l)

print(f"\n--- Page title ---")
title_m = re.search(r'<title>([^<]+)</title>', html)
if title_m:
    print(title_m.group(1))