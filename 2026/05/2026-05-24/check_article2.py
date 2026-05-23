#!/usr/bin/env python3
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    resp = pg.goto("https://downbeat.com/reviews/detail/over-the-moons", timeout=15000)
    print(f"URL after goto: {pg.url}")
    print(f"Response status: {resp.status if resp else None}")
    pg.wait_for_timeout(3000)
    print(f"URL after wait: {pg.url}")
    print(f"Final body text: {len(pg.inner_text('body'))} chars")
    print(f"Final content: {len(pg.content())} chars")
    # Check cookies
    cookies = ctx.cookies()
    print(f"Cookies: {[c['name'] for c in cookies]}")
    b.close()