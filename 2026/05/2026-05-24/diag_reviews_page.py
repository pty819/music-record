#!/usr/bin/env python3
"""Debug JazzTimes reviews page."""
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

    print("=== REVIEWS PAGE ===")
    try:
        resp = page.goto(f"{SITE_URL}/reviews", timeout=30000, wait_until="domcontentloaded")
        print(f"Status: {resp.status if resp else 'none'}")
    except Exception as e:
        print(f"Error: {e}")
        try:
            page.goto(f"{SITE_URL}/reviews", timeout=15000, wait_until="commit")
            print("commit navigation succeeded")
        except Exception as e2:
            print(f"commit also failed: {e2}")
    page.wait_for_timeout(3000)
    print(f"URL: {page.url}")

    # Print all links on page
    print("\n=== ALL LINKS ===")
    all_a = page.query_selector_all("a")
    for el in all_a:
        href = el.get_attribute("href")
        if not href:
            continue
        text = el.inner_text().strip()[:80]
        if 'jazztimes' in href or href.startswith('/'):
            print(f"  {href[:120]} | {text}")

    # Print pagination links
    print("\n=== PAGINATION LINKS ===")
    for el in all_a:
        href = el.get_attribute("href")
        if not href:
            continue
        text = el.inner_text().strip()
        if 'page' in href.lower() or text.isdigit():
            print(f"  href={href} | text={text}")

    # Print links that are actual review articles (have slugs)
    print("\n=== REVIEW ARTICLE LINKS ===")
    for el in all_a:
        href = el.get_attribute("href")
        if not href:
            continue
        if '/reviews/' in href:
            if href.startswith('/'):
                href = urljoin(SITE_URL, href)
            # Skip index pages
            if re.match(r'https://www\.jazztimes\.com/reviews/?$', href):
                continue
            if re.match(r'https://www\.jazztimes\.com/reviews/[a-z]+/?$', href):
                continue
            text = el.inner_text().strip()[:80]
            print(f"  {href[:120]} | {text}")

    browser.close()