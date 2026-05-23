#!/usr/bin/env python3
import re, sys, time, json
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.11/site_packages')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto("https://www.truthandliesmusic.com/", timeout=15000)
    time.sleep(3)

    # Check all links on homepage
    links = page.query_selector_all("a")
    print(f"Total links: {len(links)}")
    for l in links:
        href = l.get_attribute("href") or ""
        text = l.inner_text().strip()[:80]
        if href:
            print(f"  href={repr(href)} text={repr(text)}")

    # Try different nav sections
    for url in [
        "https://www.truthandliesmusic.com/reviews",
        "https://www.truthandliesmusic.com/category/reviews",
        "https://www.truthandliesmusic.com/category/music",
    ]:
        page.goto(url, timeout=15000)
        time.sleep(2)
        links2 = page.query_selector_all("a")
        print(f"\n{url}: {len(links2)} links")
        for l in links2:
            href = l.get_attribute("href") or ""
            text = l.inner_text().strip()[:80]
            if href and "/20" in href:
                print(f"  href={repr(href)} text={repr(text)}")

    browser.close()