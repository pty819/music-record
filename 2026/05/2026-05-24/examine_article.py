#!/usr/bin/env python3
import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews/detail/over-the-moons", timeout=15000)
    pg.wait_for_timeout(1500)

    print("=== Full HTML (article page) ===")
    html = pg.content()
    print(html[:8000])
    b.close()