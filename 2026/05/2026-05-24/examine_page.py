#!/usr/bin/env python3
import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews", timeout=20000)
    pg.wait_for_timeout(2000)

    print("=== All hrefs on page ===")
    for a in pg.query_selector_all("a"):
        href = a.get_attribute("href")
        txt = (a.inner_text() or "").strip()[:60]
        if href and "/reviews" in href:
            print(f"  {href!r:80s}  text={txt!r}")

    print("\n=== All hrefs with /reviews/detail/ ===")
    for a in pg.query_selector_all("a[href*='/reviews/detail/']"):
        href = a.get_attribute("href")
        print(f"  {href}")

    print("\n=== Looking for article cards ===")
    for sel in [".review-card", ".article-card", ".card", ".review-item", "[class*='review']", "[class*='article']"]:
        els = pg.query_selector_all(sel)
        if els:
            print(f"  {sel}: {len(els)} found")
            for e in els[:3]:
                print(f"    {e.inner_html()[:100]}")

    print("\n=== HTML structure (first 3000 chars) ===")
    html = pg.content()
    # Find the main content area
    body_idx = html.find("<body")
    if body_idx >= 0:
        print(html[body_idx:body_idx+3000])

    b.close()