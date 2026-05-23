#!/usr/bin/env python3
import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews/detail/over-the-moons", timeout=15000)
    pg.wait_for_timeout(2000)
    html = pg.content()

    # Stars
    for m in re.finditer("font_awesome_star_rank", html):
        start = max(0, m.start()-100)
        end = min(len(html), m.end()+200)
        print("STARS:", repr(html[start:end]))
        print("---")

    # Also try to get the rating div
    for sel in [".rating", "[class*='star']", ".album-rating"]:
        el = pg.query_selector(sel)
        if el:
            print(f"Selector {sel!r}: {el.inner_html()[:200]}")

    # Post info text
    postinfo = pg.query_selector(".postinfo")
    if postinfo:
        print(f"postinfo: {postinfo.inner_html()}")

    # Get the rating from visible text
    for el in pg.query_selector_all(".pad-btm-sm"):
        txt = el.inner_text()
        if txt and ("star" in txt.lower() or "/" in txt):
            print(f"pad-btm-sm: {txt!r}")

    b.close()