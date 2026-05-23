#!/usr/bin/env python3
"""Inspect JazzTimes homepage pagination."""
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
    print(f"Title: {page.title()}")

    # Find all links with page numbers
    print("\n=== PAGINATION LINKS ===")
    for a in page.query_selector_all("a"):
        href = a.get_attribute("href")
        text = a.inner_text().strip()
        if not href: continue
        # Look for pagination indicators
        if re.search(r'/page/\d+|page=\d+|/P\d+|\?v=', href) or text.isdigit() or text == 'Next' or text == '»':
            print(f"  href={href} | text={text}")

    # Also check if there's a "load more" button
    print("\n=== LOAD MORE / INFINITE SCROLL ===")
    for sel in ["[class*='load']","[class*='more']","[class*='pagination']","[class*='page']","button"]:
        try:
            els = page.query_selector_all(sel)
            for el in els:
                t = el.inner_text().strip()
                if t:
                    print(f"  {sel}: {t[:50]}")
        except: pass

    # Check what the current page number is and what comes after
    print("\n=== ALL ARTICLE-LIKE LINKS (with /2026/ or real slugs) ===")
    for a in page.query_selector_all("a"):
        href = a.get_attribute("href")
        if not href: continue
        text = a.inner_text().strip()
        if '/2026/' in href or '/2025/' in href:
            if href.startswith('/'): href = urljoin(SITE_URL, href)
            print(f"  {href[:100]} | {text[:50]}")

    browser.close()