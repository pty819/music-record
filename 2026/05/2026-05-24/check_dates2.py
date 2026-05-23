#!/usr/bin/env python3
"""Check dates of articles found via homepage."""
import sys
sys.path.insert(0, '/home/liyifan/music-record')
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import re
from datetime import datetime, timedelta, timezone

SITE_URL = "https://www.jazztimes.com"
UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=3)

print(f"Today: {NOW.date()}, CUTOFF: {CUTOFF.date()}\n")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage"],
        executable_path="/usr/bin/chromium"
    )
    ctx = browser.new_context(user_agent=UA)
    page = ctx.new_page()

    page.goto(SITE_URL, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    for sel in ["button:has-text('Accept')","button:has-text('Agree')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(1500)
                break
        except: pass

    try:
        page.wait_for_selector("article,[class*='post'],.post-list", timeout=5000)
    except: pass

    print("=== ALL ARTICLE URLS FROM HOMEPAGE ===")
    count = 0
    for a in page.query_selector_all("a"):
        href = a.get_attribute("href")
        if not href: continue
        if '/reviews/' in href or '/features/' in href:
            if href.startswith('/'): href = urljoin(SITE_URL, href)
            if re.match(r'https://www\.jazztimes\.com/(reviews|features)/?[a-z-]*$', href): continue

            # Get date from article itself
            try:
                article = ctx.new_page()
                article.goto(href, timeout=15000, wait_until="domcontentloaded")
                article.wait_for_timeout(1500)

                dt = ""
                for sel in ["time[datetime]"]:
                    try:
                        el = article.query_selector(sel)
                        if el: dt = el.get_attribute("datetime") or ""; break
                    except: pass

                print(f"  {dt[:10]} | {href[:100]}")
                article.close()
                count += 1
                if count >= 15:
                    break
            except Exception as e:
                print(f"  ERROR | {href[:80]} | {e}")
                try: article.close()
                except: pass

    browser.close()