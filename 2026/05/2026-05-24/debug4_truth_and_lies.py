#!/usr/bin/env python3
import re, sys, time
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.11/site_packages')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto("https://www.truthandliesmusic.com/magazine", timeout=15000)
    time.sleep(3)

    # Check for article elements
    articles = page.query_selector_all("article")
    print(f"Article elements: {len(articles)}")

    # Try different selectors
    for sel in ["article a", ".post a", ".entry a", "h2 a", ".item a"]:
        els = page.query_selector_all(sel)
        print(f"Selector '{sel}': {len(els)} found")
        for e in els[:3]:
            href = e.get_attribute("href") or ""
            if href and "magazine" in href:
                print(f"  -> {repr(href)} | {repr(e.inner_text()[:60])}")

    # Get HTML structure around posts
    body = page.inner_html()
    print("\nHTML sample (first 2000 chars):")
    print(body[:2000])
    browser.close()