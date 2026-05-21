import urllib.request
import re, json, html
from datetime import datetime, timedelta

ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (compatible; PostPunkScraper/1.0)"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read().decode("utf-8", errors="replace")

def strip(t):
    t = re.sub(r'<[^>]+>', '', t)
    t = html.unescape(t)
    return re.sub(r'\s+', ' ', t).strip()

today = datetime.now()
cutoff = today - timedelta(days=3)
print(f"Today: {today.date()}, Cutoff: {cutoff.date()}")

# --- Get homepage to find article links ---
home = fetch("https://post-punk.com/")
# Find all article URLs and their approximate dates
# The site uses data-date or published date patterns
article_links = re.findall(r'href="(https://post-punk\.com/[^"?]+)"[^>]*>\s*([^<]{10,100})\s*<', home)
print(f"\nHomepage article links found: {len(article_links)}")

# Find date mentions near links
# Extract all date patterns from homepage
all_dates = re.findall(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{1,2}),?\s*(\d{4})', home, re.I)
date_positions = []
for m in re.finditer(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(\d{1,2}),?\s*(\d{4})', home, re.I):
    date_positions.append((m.start(), m.group(1).title(), m.group(2), m.group(3)))

# Get actual URLs from homepage with dates
# The homepage has article blocks with title and date nearby
article_blocks = re.findall(r'<a[^>]+href="(https://post-punk\.com/[^"?]+)"[^>]*>\s*<[^>]*>\s*([^<]{10,200})\s*<', home)
print(f"Article blocks: {len(article_blocks)}")
for u, t in article_blocks[:10]:
    print(f"  {u} -> {t[:70]}")

# Let's parse properly - find article cards with datePublished
articles_raw = re.findall(r'"@type":"Article"[^}]+\{"@type":"Person"[^}]*"name":"([^"]+)"[^}]+\}[^}]+"datePublished":"([^"]+)"[^}]+"headline":"([^"]+)"[^}]+\}', home, re.DOTALL)
print(f"\nJSON-LD articles: {len(articles_raw)}")
for author, date, headline in articles_raw[:10]:
    print(f"  {date[:10]} | {author} | {headline[:60]}")

# Alternative: find all post URLs from homepage
post_urls = re.findall(r'"(https://post-punk\.com/[^"]+)"[^}]*"datePublished"\s*:\s*"([^"]+)"', home)
print(f"\nURLs with datePublished: {len(post_urls)}")
for url, date in post_urls[:15]:
    print(f"  {date[:10]} | {url}")

# Also look for /2026/ URLs
urls_2026 = re.findall(r'href="(https://post-punk\.com/[^"?]*2026[^"?]*)"', home)
print(f"\n/2026/ URLs: {len(urls_2026)}")
for u in urls_2026[:20]:
    print(f"  {u}")
