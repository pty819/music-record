#!/usr/bin/env python3
"""Inspect JazzTimes article HTML."""
import sys
sys.path.insert(0, '/home/liyifan/music-record')
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

url = 'https://www.jazztimes.com/reviews/live/tyshawn-sorey-piano-concerto-for-marilyn-crispell-featuring-aaron-diehl-has-its-philly-hosted-world-premiere/'

UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage"],
        executable_path="/usr/bin/chromium"
    )
    ctx = browser.new_context(user_agent=UA)
    page = ctx.new_page()

    try:
        resp = page.goto(url, timeout=15000, wait_until="domcontentloaded")
        print(f"Status: {resp.status if resp else 'none'}")
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"Error: {e}")

    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")

    html = page.content()
    print(f"HTML length: {len(html)}")

    # Check for paywall indicators
    for keyword in ['paywall', 'subscriber', 'subscribe', 'premium', 'sign in to continue', 'metered']:
        if keyword in html.lower():
            print(f"Found paywall keyword: {keyword}")

    # Print first 500 chars of body
    body = page.query_selector("body")
    if body:
        text = body.inner_text()[:500]
        print(f"Body text (500 chars): {text}")

    browser.close()