#!/usr/bin/env python3
import subprocess, re

def curl(url):
    result = subprocess.run([
        'curl', '-s', '--max-time', '20', '-L', '-A',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        url
    ], capture_output=True, text=True)
    return result.stdout

# Fetch an article page and look for score and date patterns
html = curl('https://thequietus.com/quietus-reviews/speedy-j-walkman-review/')

# Find all class attributes that contain 'score'
score_classes = re.findall(r'class="[^"]*score[^"]*"[^>]*>', html, re.IGNORECASE)
print("Score-related HTML:")
for s in score_classes[:10]:
    print(f"  {s}")

# Find all class attributes that contain 'date'
date_classes = re.findall(r'class="[^"]*date[^"]*"[^>]*>', html, re.IGNORECASE)
print("\nDate-related HTML:")
for d in date_classes[:10]:
    print(f"  {d}")

# Find all class attributes that contain 'rating'
rating_classes = re.findall(r'class="[^"]*rating[^"]*"[^>]*>', html, re.IGNORECASE)
print("\nRating-related HTML:")
for r in rating_classes[:10]:
    print(f"  {r}")

# Find the article body
article = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
if article:
    article_html = article.group(1)
    # Find score patterns in article text
    scores = re.findall(r'(\d+(?:\.\d+)?)\s*/\s*10', article_html)
    print(f"\nScores found in article: {scores}")
    
    # Print some of the article content
    article_text = re.sub(r'<[^>]+>', ' ', article_html)
    article_text = re.sub(r'\s+', ' ', article_text).strip()
    print(f"\nArticle text (first 1000 chars):\n{article_text[:1000]}")

# Check if there's a meta tag with rating
meta_rating = re.findall(r'<meta[^>]+property="[^"]*rating[^"]*"[^>]*>', html, re.IGNORECASE)
print(f"\nMeta rating tags: {meta_rating[:5]}")