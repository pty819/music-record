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

    for m in re.finditer("Published", html):
        start = max(0, m.start()-100)
        end = min(len(html), m.end()+200)
        print(repr(html[start:end]))
        print("---")

    b.close()