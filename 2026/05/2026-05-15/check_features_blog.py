import urllib.request
import ssl
import re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return resp.read().decode('utf-8', errors='replace')

# The blog page (newsID=1903) is "Shaking the Squid" - a blog post linking recent reviews
# Let me check if there are pagination links on the blog page by looking for
# any pattern like "older posts" or numbered pages

url = 'https://www.squidco.com/cgi-bin/news/newsView.cgi?newsID=1903'
html = fetch(url)

# Look for pagination patterns - older posts, newer posts, page numbers
print('Looking for pagination patterns:')
for pattern in [r'Older Posts', r'Newer Posts', r'older', r'newer', r'previous', r'next', r'<<', r'>>', r'page \d+']:
    m = re.findall(pattern, html, re.IGNORECASE)
    if m:
        print(f'  Found: {m[:5]}')

# Try to find any hidden links
links = re.findall(r"<a[^>]+href=['\"][^'\"]+newsID=(\d+)[^'\"]*['\"][^>]*>([^<]*)</a>", html)
print(f'\nAll links with newsID: {len(links)}')
for nid, text in links[-15:]:
    print(f'  newsID={nid}: {text[:60]}')

# Let me also check if there's another blog listing page
# The blog.shtml was 404, so maybe the blog is only accessible via specific newsIDs
# Let me try to find blog post IDs near 1903
print('\n\nChecking nearby newsIDs for more blog posts:')
for nid in [1900, 1901, 1902, 1903, 1904, 1905]:
    url2 = f'https://www.squidco.com/cgi-bin/news/newsView.cgi?newsID={nid}'
    html2 = fetch(url2)
    title_m = re.search(r'<title>(.*?)</title>', html2)
    title = title_m.group(1)[:60] if title_m else 'NO TITLE'
    m = re.search(r'&nbsp;&nbsp;(\d{4}-\d{2}-\d{2})</font>', html2)
    date = m.group(1) if m else 'NO DATE'
    # Check if this is a listing page (has many newsID links)
    ids = re.findall(r'newsID=(\d+)', html2)
    print(f'  newsID={nid}: date={date}, title={title}, links={len(set(ids))}')
