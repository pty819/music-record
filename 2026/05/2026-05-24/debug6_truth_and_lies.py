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

    articles = page.query_selector_all("article")
    print(f"Articles: {len(articles)}")

    # Get just the first link in each article
    for i, article in enumerate(articles[:3]):
        first_link = article.query_selector("a")
        href = first_link.get_attribute("href") if first_link else ""
        text = first_link.inner_text().strip() if first_link else ""
        print(f"Article {i}: text={repr(text[:50])} href={repr(href)}")
        print(f"  ALL links in this article:")
        all_links = article.query_selector_all("a")
        for l in all_links:
            href2 = l.get_attribute("href") or ""
            text2 = l.inner_text().strip()[:50]
            print(f"    [{repr(text2)}] -> {repr(href2)}")

    browser.close()