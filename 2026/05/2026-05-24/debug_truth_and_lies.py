#!/usr/bin/env python3
import re, sys, time
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.11/site_packages')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto("https://www.truthandliesmusic.com/", timeout=15000)
    time.sleep(3)

    # Get all links
    links = page.query_selector_all("a")
    date_links = [l for l in links if re.search(r'/\d{4}/\d{2}/', l.get_attribute("href") or "")]
    print(f"Total links: {len(links)}, Date links: {len(date_links)}")
    for l in date_links[:20]:
        print(repr(l.get_attribute("href")), '|', l.inner_text()[:80])
    print("---PAGE TITLE:", page.title())
    print("---URL:", page.url)
    browser.close()