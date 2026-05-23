#!/usr/bin/env python3
"""ProgArchives scraper - Cloudflare blocked, returns empty with status."""
import sys
sys.path.insert(0, '/usr/local/lib/python3.12/site-packages')

import json
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-24/progarchives_reviews.json"

def detect_block(page):
    try:
        if "Just a moment" in page.title():
            return True
        if "Ray ID" in page.content() and "security" in page.content():
            return True
    except:
        pass
    return False

def scrape():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        print("Navigating to https://www.progarchives.com/ ...")
        try:
            page.goto("https://www.progarchives.com/", timeout=45000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation failed: {e}")
            browser.close()
            return []

        print(f"Title: {page.title()}")

        if detect_block(page):
            print("Cloudflare blocking detected.")
            browser.close()
            return []

        browser.close()
        return []

if __name__ == "__main__":
    print("=== ProgArchives Scraper ===")
    items = scrape()
    print(f"\nScraped {len(items)} items")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"Written to {OUTPUT_FILE}")