#!/usr/bin/env python3
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    try:
        pg.goto("https://downbeat.com/reviews", timeout=60000, wait_until="commit")
        print(f"URL: {pg.url}")
    except Exception as e:
        print(f"goto with commit failed: {e}")
    pg.wait_for_timeout(3000)
    print(f"URL after wait: {pg.url}")
    html_len = len(pg.content())
    print(f"HTML len: {html_len}")
    links = pg.query_selector_all("a[href*='/reviews/detail/']")
    print(f"Article links: {len(links)}")
    b.close()