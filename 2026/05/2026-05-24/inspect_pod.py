#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/python3/dist-packages')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://pointofdeparture.org/", timeout=30000)
    page.wait_for_timeout(3000)

    # Handle cookie banner
    try:
        accept_btn = page.get_by_text("Accept").first
        accept_btn.click()
        page.wait_for_timeout(1000)
    except Exception:
        pass

    # Get page content for inspection
    content = page.content()

    # Print first 8000 chars
    print(content[:8000])
    browser.close()