#!/usr/bin/env python3
import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews", timeout=15000)
    pg.wait_for_timeout(2000)

    # Check what dates appear on the listing page
    html = pg.content()

    # Look for star rankings on listing page
    for term in ["star_rank", "fa-star", "font_awesome"]:
        positions = [m.start() for m in re.finditer(term, html, re.I)]
        if positions:
            print(f"{term!r}: {len(positions)} occurrences")
            for pos in positions[:3]:
                print(f"  {html[max(0,pos-60):pos+120]!r}")

    # Look for anything that looks like dates or issue numbers on the listing
    for term in ["May 2026", "June 2026", "2026", "issue"]:
        positions = [m.start() for m in re.finditer(term, html, re.I)]
        if positions:
            print(f"{term!r}: {len(positions)} occurrences")
            for pos in positions[:2]:
                print(f"  {html[max(0,pos-80):pos+80]!r}")

    # Get the article cards HTML
    print("\n\n=== Article cards ===")
    for a in pg.query_selector_all("a[href*='/reviews/detail/']"):
        href = a.get_attribute("href")
        # Get surrounding HTML
        outer = a.inner_html()
        txt = a.inner_text()
        print(f"href={href!r}")
        print(f"  text={txt[:200]!r}")
        print()

    b.close()