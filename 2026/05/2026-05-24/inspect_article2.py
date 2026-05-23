#!/usr/bin/env python3
"""Debug visit_article with full output."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

SITE = "jazztimes"
SITE_URL = "https://www.jazztimes.com"
DAYS = 3
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=DAYS)

UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"

url = 'https://www.jazztimes.com/reviews/live/tyshawn-sorey-piano-concerto-for-marilyn-crispell-featuring-aaron-diehl-has-its-philly-hosted-world-premiere/'

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage"],
        executable_path="/usr/bin/chromium"
    )
    ctx = browser.new_context(user_agent=UA)
    page = ctx.new_page()

    print(f"Going to: {url}")
    try:
        resp = page.goto(url, timeout=15000, wait_until="domcontentloaded")
        print(f"Status: {resp.status if resp else 'none'}")
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"Error: {e}")
        browser.close()
        exit(1)

    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")

    html = page.content()
    print(f"HTML length: {len(html)}")

    # Check page content
    body = page.query_selector("body")
    if body:
        text = body.inner_text()[:300]
        print(f"Body text (300 chars):\n{text}")

    # Check for Cloudflare
    if 'cloudflare' in html.lower() or 'cf-' in html.lower():
        print("CLOUDFLARE detected in HTML!")

    # Check what the h1 says
    h1 = page.query_selector("h1")
    if h1:
        print(f"H1: {h1.inner_text()}")

    # Check byline
    for sel in ["[class*='byline']",".author","[class*='author']","[class*='by-line']"]:
        try:
            el = page.query_selector(sel)
            if el:
                print(f"Byline ({sel}): {el.inner_text()}")
        except: pass

    # Check date
    for sel in ["time[datetime]","[class*='date']",".post-date",".entry-date"]:
        try:
            el = page.query_selector(sel)
            if el:
                dt = el.get_attribute("datetime")
                txt = el.inner_text()
                print(f"Date ({sel}): datetime={dt}, text={txt}")
        except: pass

    # Check score
    for sel in ["[class*='score']","[class*='rating']","[itemprop='ratingValue']"]:
        try:
            el = page.query_selector(sel)
            if el:
                print(f"Score ({sel}): {el.inner_text()}")
        except: pass

    # Check excerpt
    for sel in ["[class*='excerpt']","[class*='summary']","[class*='lede']","[class*='lead']"]:
        try:
            el = page.query_selector(sel)
            if el:
                print(f"Excerpt ({sel}): {el.inner_text()[:200]}")
        except: pass

    browser.close()
    print("\nDone.")