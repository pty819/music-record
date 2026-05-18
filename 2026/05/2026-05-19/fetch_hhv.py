import urllib.request, re, json

def fetch_html(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return f"ERROR: {e}"

url = 'https://www.hhv-mag.com/review/earl-sweatshirt-mike-surf-gang-pompeii-utility'
html = fetch_html(url)
print(f"Length: {len(html)}")

# Look for date patterns
patterns = [
    r'(\d{1,2}\.\s*[A-Za-zäöüß]+\s*\d{4})',
    r'(\d{4}-\d{2}-\d{2})',
    r'(published.*?\d{4})',
    r'(date.*?\d{4})',
]
for p in patterns:
    matches = re.findall(p, html[:5000], re.IGNORECASE)
    if matches:
        print(f"Pattern {p}: {matches[:5]}")

# Look for JSON-LD
jsonld = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
for j in jsonld:
    print(f"JSON-LD: {j[:500]}")
