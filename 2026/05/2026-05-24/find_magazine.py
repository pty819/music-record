#!/usr/bin/env python3
import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews", timeout=30000)
    pg.wait_for_timeout(2000)
    html = pg.content()

    # Find all magazine hrefs
    for m in re.finditer(r'magazine', html, re.I):
        start = max(0, m.start()-30)
        end = min(len(html), m.end()+60)
        print(repr(html[start:end]))
    b.close()