#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/python3.12/site-packages')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=Automation"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    )
    page = context.new_page()
    page.goto("https://www.progarchives.com/", timeout=30000, wait_until="domcontentloaded")
    print("Title:", page.title())
    print("URL:", page.url)
    page.wait_for_timeout(3000)
    print("Title after wait:", page.title())
    print("URL after wait:", page.url)
    
    # Check for cookie button
    for selector in ["#accept", "button.accept", "[aria-label*='Accept']", "button:has-text('Accept')"]:
        try:
            btn = page.query_selector(selector)
            if btn:
                print(f"Found button: {selector} = {btn.is_visible()}")
        except:
            pass
    
    # Get page content snippet
    body = page.inner_text("body")
    print("Body snippet (500 chars):", body[:500])
    
    browser.close()