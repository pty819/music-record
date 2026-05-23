#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/python3/dist-packages')

from playwright.sync_api import sync_playwright
import re

def extract_text(el):
    if not el:
        return ""
    return el.inner_text().strip()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Check Content.html (current issue)
    page.goto("https://pointofdeparture.org/Content.html", timeout=30000)
    page.wait_for_timeout(3000)
    print("=== Content.html (current issue) ===")
    print(page.content()[:6000])
    browser.close()