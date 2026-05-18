import urllib.request, re

def fetch_text(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return f"ERROR: {e}"

# Try to get the review page raw HTML
url = 'https://www.hhv-mag.com/review/earl-sweatshirt-mike-surf-gang-pompeii-utility'
html = fetch_text(url)
print(f"Length: {len(html)}")

# Search for date patterns in HTML
date_patterns = [
    r'(\d{1,2}\.\s*[A-Z][a-zäöü]+\s*\d{4})',
    r'(\d{4}-\d{2}-\d{2})',
    r'publi[sz]ed[^<]{0,50}',
    r'article:published_time[^<]',
]
for p in date_patterns:
    matches = re.findall(p, html[:10000], re.IGNORECASE)
    if matches:
        print(f"  {p}: {matches[:5]}")

# Also try to find meta tags
meta_dates = re.findall(r'<meta[^>]*(?:published|updated|article:published_time)[^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
print(f"Meta dates: {meta_dates}")

# Try to find the author/date in the article header
header = re.findall(r'class="[^"]*date[^"]*"[^>]*>([^<]+)', html, re.IGNORECASE)
print(f"Date classes: {header[:5]}")

# Find JSON-LD
jsonld = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
for j in jsonld:
    print(f"JSON-LD: {j[:300]}")
