#!/usr/bin/env python3
"""Debug JazzTimes listing page structure."""
import sys
sys.path.insert(0, '/home/liyifan/music-record')
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

SITE_URL = "https://www.jazztimes.com"

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context()
    page = context.new_page()

    print("=== HOME PAGE ===")
    page.goto(SITE_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)
    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")

    # Print all links with their text and href
    print("\n=== ALL LINKS WITH TEXT ===")
    for sel in ["a"]:
        els = page.query_selector_all(sel)
        for el in els:
            href = el.get_attribute("href")
            text = el.inner_text().strip()[:60]
            if href and ('jazztimes' in href or href.startswith('/')):
                print(f"  {href[:100]} | {text}")

    # Get article URLs
    print("\n=== ARTICLE LINKS WITH YEAR ===")
    for sel in ["article a", ".post-list a", "[class*='post'] a"]:
        els = page.query_selector_all(sel)
        for el in els:
            href = el.get_attribute("href")
            text = el.inner_text().strip()[:80]
            if href and ('/2026/' in href or '/2025/' in href):
                print(f"  {href[:120]} | {text}")

    browser.close()