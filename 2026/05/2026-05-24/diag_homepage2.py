#!/usr/bin/env python3
"""Debug JazzTimes homepage with wait_for."""
import sys
sys.path.insert(0, '/home/liyifan/music-record')
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import re

SITE_URL = "https://www.jazztimes.com"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        executable_path="/usr/bin/chromium"
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"
    )
    page = context.new_page()

    print("=== HOME PAGE ===")
    resp = page.goto(SITE_URL, timeout=30000, wait_until="domcontentloaded")
    print(f"Status: {resp.status if resp else 'none'}")
    page.wait_for_timeout(5000)
    print(f"URL: {page.url}")

    # Wait for articles to load
    print("\n=== WAITING FOR ARTICLE SECTION ===")
    try:
        page.wait_for_selector("article, [class*='post'], .post-list", timeout=5000)
        print("Articles section found!")
    except Exception as e:
        print(f"Timeout waiting for articles: {e}")

    # Count total links
    all_links = page.query_selector_all("a")
    print(f"\nTotal links on page: {len(all_links)}")

    # Find recent article links
    print("\n=== ARTICLE LINKS ===")
    count = 0
    for a in all_links:
        href = a.get_attribute("href")
        if not href:
            continue
        if '/reviews/' in href or '/features/' in href or '/blog/' in href:
            if href.startswith('/'):
                href = urljoin(SITE_URL, href)
            if re.match(r'https://www\.jazztimes\.com/(reviews|features|blog)/?$', href):
                continue
            if re.match(r'https://www\.jazztimes\.com/(reviews|features)/[a-z-]+/?$', href):
                continue
            text = a.inner_text().strip()[:80]
            print(f"  {href[:120]} | {text[:60]}")
            count += 1
            if count >= 30:
                break

    print(f"\nTotal shown: {count}")

    browser.close()