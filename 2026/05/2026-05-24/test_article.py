#!/usr/bin/env python3
import traceback
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    pg = ctx.new_page()
    pg.goto("https://downbeat.com/reviews", timeout=20000)
    pg.wait_for_timeout(1000)

    links = []
    for a in pg.query_selector_all("a[href*='/reviews/']"):
        href = a.get_attribute("href")
        if href:
            if not href.startswith("http"):
                href = "https://downbeat.com" + href
            if "/reviews/" in href:
                links.append(href)
    links = list(dict.fromkeys(links))
    print(f"Found {len(links)} links")

    for url in links[:5]:
        print(f"\n--- {url} ---")
        try:
            ap = ctx.new_page()
            ap.goto(url, timeout=15000)
            ap.wait_for_timeout(1000)
            try:
                txt = ap.inner_text("body")
                print(f"inner_text(body): {len(txt)} chars")
            except Exception as e:
                print(f"inner_text error: {e}")
            try:
                c = ap.content()
                print(f"content(): {len(c)} chars")
            except Exception as e:
                print(f"content error: {e}")
            ap.close()
        except Exception as e:
            print(f"goto error: {e}")
            traceback.print_exc()
    b.close()