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

    # Check article 0 in detail
    a0 = articles[0]
    print(f"Article 0 tag: {a0.evaluate('el => el.tagName')}")
    print(f"Article 0 HTML (first 500): {a0.inner_html()[:500]}")
    print(f"Article 0 text: {a0.inner_text()[:200]}")

    # Try to find first <a> via evaluate
    first_a = a0.evaluate('''el => {
        const a = el.querySelector('a');
        return a ? {href: a.href, text: a.innerText} : null;
    }''')
    print(f"First <a> via evaluate: {first_a}")

    # Check direct query
    direct = a0.query_selector("a")
    print(f"query_selector('a') result: {direct}")
    browser.close()