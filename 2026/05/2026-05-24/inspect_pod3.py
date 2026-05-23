#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/python3/dist-packages')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://pointofdeparture.org/Archive.html", timeout=30000)
    page.wait_for_timeout(3000)
    print(page.content()[:8000])
    browser.close()