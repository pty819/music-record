#!/usr/bin/env python3
"""Debug visit_one for a single article."""
import json, re, sys, time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

SITE = "jazztimes"
SITE_URL = "https://www.jazztimes.com"
UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"

def parse_date(s):
    if not s: return None
    s = re.sub(r'\s+', ' ', s.strip())
    for fmt in ["%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%d",
                "%B %d, %Y","%b %d, %Y","%B %d %Y","%b %d %Y","%m/%d/%Y"]:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError: pass
    return None

def strip(t):
    if not t: return ""
    t = re.sub(r'<br\s*/?>', ' ', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:500]

def get_text(el):
    try: return el.inner_text()
    except: return el.text_content() or ""

URL = "https://www.jazztimes.com/blog/how-black-music-took-over-the-world-a-response-from-melvin-gibbs/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"], executable_path="/usr/bin/chromium")
    ctx = browser.new_context(user_agent=UA)
    page = ctx.new_page()
    print("Going to URL...")
    try:
        resp = page.goto(URL, timeout=15000, wait_until="domcontentloaded")
        print(f"Status: {resp.status if resp else 'None'}")
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"Error: {e}")
    html = page.content()
    print(f"HTML length: {len(html)}")
    if len(html) < 5000:
        print("HTML too short!")
        browser.close()
        sys.exit(1)
    title = strip(get_text(page.query_selector("h1"))) if page.query_selector("h1") else ""
    print(f"Title: '{title}'")
    date_text = ""
    for sel in ["time[datetime]","[class*='date']",".post-date",".entry-date"]:
        el = page.query_selector(sel)
        if el:
            date_text = el.get_attribute("datetime") or strip(get_text(el))
            print(f"Date sel={sel}: '{date_text}'")
            break
    browser.close()