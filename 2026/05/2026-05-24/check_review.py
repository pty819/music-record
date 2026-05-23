from playwright.sync_api import sync_playwright
import re

def clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    with browser.new_page() as page:
        page.goto("https://www.seaoftranquility.org/reviews.php?op=showcontent&id=25540", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        html = page.content()
        
        # Find the Added date
        m = re.search(r'<b>Added:</b>\s*([A-Z][a-z]+ \d+\w* \d{4})', html)
        if m:
            print("Date found:", m.group(1))
        
        # Count stars
        whole = len(re.findall('star_whole', html))
        half = len(re.findall('star_half', html))
        print("Stars:", whole, "whole,", half, "half")
        
        # Find the review body
        idx = html.find('<blockquote>')
        if idx >= 0:
            review_html = html[idx:idx+2000]
            review_text = clean_html(review_html)
            print("Review text (500):", review_text[:500])
        
        # Get title
        m = re.search(r'<title>\s*Review:\s*"([^"]+)"', html)
        if m:
            print("Title:", m.group(1))
        
        # Also check page text
        body = page.locator('body').inner_text()
        lines = [l.strip() for l in body.split('\n') if l.strip()]
        for i, line in enumerate(lines):
            if 'Added' in line or 'Score' in line or 'Reviewer' in line:
                print(f"Line {i}: {line}")
    browser.close()