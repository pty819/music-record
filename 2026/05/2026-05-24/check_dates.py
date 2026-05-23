#!/usr/bin/env python3
"""Check current date and JazzTimes article dates."""
import sys
sys.path.insert(0, '/home/liyifan/music-record')
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import re
from datetime import datetime, timedelta, timezone

SITE_URL = "https://www.jazztimes.com"
UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"

print(f"Today: {datetime.now(timezone.utc).date()}")
print(f"CUTOFF (3 days ago): {(datetime.now(timezone.utc) - timedelta(days=3)).date()}")
print()

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
    page.wait_for_selector("article,[class*='post'],.post-list", timeout=5000)

    print("=== HOMEPAGE ARTICLES WITH DATES ===")
    for a in page.query_selector_all("a"):
        href = a.get_attribute("href")
        if not href: continue
        if '/2026/' not in href and '/2025/' not in href: continue
        if href.startswith('/'): href = urljoin(SITE_URL, href)
        # Skip index pages
        if re.match(r'https://www\.jazztimes\.com/(reviews|features|blog)/?[a-z-]*$', href): continue

        # Visit each article link to get its date
        try:
            article = ctx.new_page()
            article.goto(href, timeout=15000, wait_until="domcontentloaded")
            article.wait_for_timeout(2000)

            dt = ""
            for sel in ["time[datetime]"]:
                try:
                    el = article.query_selector(sel)
                    if el:
                        dt = el.get_attribute("datetime") or ""
                        break
                except: pass

            print(f"  {dt[:10]} | {href[:100]}")
            article.close()
        except Exception as e:
            print(f"  ERROR | {href[:100]} | {e}")
            try: article.close()
            except: pass

    browser.close()