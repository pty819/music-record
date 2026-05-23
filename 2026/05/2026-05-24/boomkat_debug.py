#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/liyifan/.hermes/hermes-agent/venv/lib/python3.11/site-packages')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    page.goto("https://boomkat.com/", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    # Cookie
    for selector in ["button[aria-label*='Accept']", "button[aria-label*='Agree']", "text=Accept", "text=Agree", "text=OK", "#onetrust-accept-btn-handler"]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                el.click()
                print(f"Clicked: {selector}")
                break
        except Exception:
            pass
    page.wait_for_timeout(2000)

    # Navigate to in-writing
    page.goto("https://boomkat.com/in-writing", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    # Snapshot the page
    print("=== PAGE TITLE ===")
    print(page.title())
    print("=== SNAPSHOT ===")
    snapshot = page.content()
    print(snapshot[:5000])
    print("=== END ===")

    browser.close()