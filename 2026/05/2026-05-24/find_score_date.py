#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import re

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews/detail/over-the-moons", timeout=15000)
    pg.wait_for_timeout(2000)
    html = pg.content()

    # Look for score indicators
    for term in ["score", "rating", "/10", "stars", "★★★★"]:
        positions = [m.start() for m in re.finditer(term, html, re.I)]
        if positions:
            print(f"{term!r}: {len(positions)} occurrences")
            for pos in positions[:3]:
                print(f"  context: {html[max(0,pos-50):pos+80]!r}")

    # Look for date indicators
    for term in ["2026", "2025", "datePublished", "publish-date", "pub-date"]:
        positions = [m.start() for m in re.finditer(term, html, re.I)]
        if positions:
            print(f"{term!r}: {len(positions)} occurrences")
            for pos in positions[:3]:
                print(f"  context: {html[max(0,pos-50):pos+80]!r}")

    # Look for class names near score info
    m = re.search(r'class="[^"]*score[^"]*"[^>]*>([^<]+)', html, re.I)
    if m:
        print(f"Score from class: {m.group(0)!r}")

    b.close()