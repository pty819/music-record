#!/usr/bin/env python3
import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews/detail/over-the-moons", timeout=15000)
    pg.wait_for_timeout(3000)
    html = pg.content()
    for term in ["Yuhan Su", "Over the Moons", "article-body", "score", "inner-text", "class="]:
        positions = [m.start() for m in re.finditer(term, html, re.I)]
        if positions:
            print(f"{term!r}: {len(positions)} occurrences, first at {positions[0]}")
            print(f"  context: {html[max(0,positions[0]-20):positions[0]+60]!r}")
    b.close()