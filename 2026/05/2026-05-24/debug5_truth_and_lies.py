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

    # Get article elements and their links
    articles = page.query_selector_all("article")
    print(f"Articles: {len(articles)}")

    for i, article in enumerate(articles[:5]):
        links = article.query_selector_all("a")
        print(f"\nArticle {i}: {len(links)} links")
        for l in links:
            href = l.get_attribute("href") or ""
            text = l.inner_text().strip()[:80]
            if href and text:
                print(f"  [{repr(text[:30])}] -> {repr(href)}")

    # Try getting just review-type links
    all_magazine_links = page.query_selector_all("a[href*='/magazine/']")
    print(f"\nTotal /magazine/ links: {len(all_magazine_links)}")
    for l in all_magazine_links[:10]:
        href = l.get_attribute("href") or ""
        text = l.inner_text().strip()[:80]
        print(f"  {repr(text)} -> {repr(href)}")

    browser.close()