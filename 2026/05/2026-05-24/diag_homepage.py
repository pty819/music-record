#!/usr/bin/env python3
"""Debug JazzTimes homepage links."""
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
    try:
        resp = page.goto(SITE_URL, timeout=30000, wait_until="domcontentloaded")
        print(f"Status: {resp.status if resp else 'none'}")
    except Exception as e:
        print(f"Error: {e}")
    page.wait_for_timeout(3000)
    print(f"URL: {page.url}")

    # Find review/article links
    # JazzTimes review articles: /reviews/albums/slug, /reviews/live/slug, /reviews/books/book-review-slug, /features/profiles/slug, etc.
    print("\n=== ARTICLE LINKS (reviews + features) ===")
    for a in page.query_selector_all("a"):
        href = a.get_attribute("href")
        if not href:
            continue
        if '/reviews/' in href or '/features/' in href or '/blog/' in href:
            if href.startswith('/'):
                href = urljoin(SITE_URL, href)
            # Skip index pages
            if re.match(r'https://www\.jazztimes\.com/(reviews|features|blog)/?$', href):
                continue
            if re.match(r'https://www\.jazztimes\.com/(reviews|features)/[a-z-]+/?$', href):
                continue
            text = a.inner_text().strip()[:80]
            # Also print date if present (blog posts have dates in text)
            print(f"  {href[:120]} | {text[:60]}")

    # Also check what's in each section listing
    for section_url in [
        f"{SITE_URL}/reviews/albums",
        f"{SITE_URL}/reviews/live",
        f"{SITE_URL}/features/interviews",
        f"{SITE_URL}/features/profiles",
    ]:
        print(f"\n=== {section_url} ===")
        try:
            resp = page.goto(section_url, timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            print(f"Status: {resp.status if resp else 'none'}, URL: {page.url}")
            # Get article links
            count = 0
            for a in page.query_selector_all("a"):
                href = a.get_attribute("href")
                if not href or '/2026/' not in href:
                    continue
                if href.startswith('/'):
                    href = urljoin(SITE_URL, href)
                text = a.inner_text().strip()[:60]
                print(f"  {href[:100]} | {text[:50]}")
                count += 1
                if count >= 10:
                    break
            if count == 0:
                print("  (no /2026/ article links found)")
        except Exception as e:
            print(f"  Error: {e}")

    browser.close()