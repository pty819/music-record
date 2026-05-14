import subprocess
import re

# Fetch the in-writing page
url = 'https://www.thewire.co.uk/in-writing'
result = subprocess.run(
    ['curl', '-s', '--max-time', '15', '-L',
     '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
     url],
    capture_output=True, text=True
)
content = result.stdout

# Search for articles - look for date patterns, titles, etc
# Search for date patterns like "May", "2026", etc
dates = re.findall(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+2026', content)
print(f"Date occurrences: {len(dates)}")
for d in dates[:10]:
    print(d)

# Search for article-related classes or IDs
article_classes = re.findall(r'class="([^"]*(?:article|review|post|entry)[^"]*)"', content, re.IGNORECASE)
print(f"\nArticle-like classes: {len(article_classes)}")
for c in article_classes[:20]:
    print(c)

# Look for JSON data embedded in page
json_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', content, re.DOTALL)
print(f"\nJSON-LD blocks: {len(json_blocks)}")
for jb in json_blocks[:3]:
    print(jb[:500])
    print("---")
