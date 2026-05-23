#!/usr/bin/env python3
"""Debug JazzTimes: find where articles are and why they might not have /2026/ in URL."""
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import re

SITE_URL = "https://www.jazztimes.com"
UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"], executable_path="/usr/bin/chromium")
    ctx = browser.new_context(user_agent=UA)
    page = ctx.new_page()

    page.goto(SITE_URL, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    page.wait_for_selector("article,[class*='post']", timeout=5000)

    print(f"URL: {page.url}")

    # Get the full HTML to examine the article list structure
    print("\n=== HTML around article list ===")
    html = page.content()
    # Find the article section
    for marker in ['class="post-list"', 'class="posts', 'id="recent', 'class="recent']:
        idx = html.lower().find(marker.lower())
        if idx >= 0:
            print(f"Found marker '{marker}' at index {idx}")
            print(html[max(0,idx-100):idx+500])
            break

    # Look for articles in the raw HTML
    print("\n=== ARTICLE HREF PATTERNS in raw HTML ===")
    import re
    hrefs = re.findall(r'href="([^"]*)"', html)
    real_article_count = 0
    for href in hrefs:
        if '/2026/' in href or '/features/profiles/' in href or '/features/interviews/' in href:
            print(f"  {href[:100]}")
            real_article_count += 1
    print(f"Total real article hrefs: {real_article_count}")

    # Now try via query_selector_all approach
    print("\n=== query_selector_all('article a') ===")
    count = 0
    for a in page.query_selector_all("article a"):
        href = a.get_attribute("href")
        if href:
            print(f"  {href[:80]} | {a.inner_text().strip()[:40]}")
            count += 1
    print(f"article a count: {count}")

    print("\n=== query_selector_all('a') - first 30 ===")
    for i, a in enumerate(page.query_selector_all("a")[:30]):
        href = a.get_attribute("href")
        if href:
            print(f"  [{i}] href={href[:80]} | text={a.inner_text().strip()[:40]}")

    browser.close()