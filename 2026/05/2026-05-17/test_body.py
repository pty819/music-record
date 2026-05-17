import subprocess, re

def curl(url):
    result = subprocess.run(['curl', '-s', '--max-time', '20', '-L', '-A',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'],
        capture_output=True, text=True)
    return result.stdout

url = 'https://thequietus.com/quietus-reviews/reissue-of-the-week/the-eighteenth-day-of-may-album-review/'
html = curl(url)
print('HTML length:', len(html))
print('Has article tag:', '<article' in html)

article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
print('Article match:', article_match is not None)
if article_match:
    print('Article content length:', len(article_match.group(1)))

article_divs = re.findall(r'<div[^>]+class="[^"]*article[^"]*"[^>]*>', html, re.IGNORECASE)
print('Article divs:', article_divs[:5])

main_content = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
if main_content:
    print('Main content length:', len(main_content.group(1)))
    
# Check what classes appear in the body
body_section = re.search(r'<body[^>]*>(.*)', html, re.DOTALL)
if body_section:
    # Find all divs with class attributes
    div_classes = re.findall(r'<div[^>]+class="([^"]+)"', body_section.group(1))
    unique = sorted(set(div_classes))
    print('Unique div classes:', unique[:30])