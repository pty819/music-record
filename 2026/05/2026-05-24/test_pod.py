#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/python3/dist-packages')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://pointofdeparture.org/", timeout=30000)
    page.wait_for_timeout(3000)
    print("Title:", page.title())
    print("URL:", page.url)
    # Check for cookie button
    content = page.content()
    if "cookie" in content.lower() or "accept" in content.lower():
        print("Cookie banner detected")
    browser.close()
    print("DONE")