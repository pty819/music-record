#!/usr/bin/env python3
"""Debug visit_article step by step."""
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

SITE = "jazztimes"
SITE_URL = "https://www.jazztimes.com"
DAYS = 3
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=DAYS)
NON_MUSIC = re.compile(r'(BLU-RAY|UHD|VOD|DVD)', re.IGNORECASE)

def strip(t):
    if not t: return ""
    t = re.sub(r'<br\s*/?>', ' ', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:500]

def get_text(el):
    try: return el.inner_text()
    except: return el.text_content() or ""

def in_window(s):
    if not s: return True
    s = re.sub(r'\s+', ' ', s.strip())
    for fmt in ["%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%d"]:
        try:
            p = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            print(f"  Parsed '{s}' -> {p.date()}")
            return p >= CUTOFF
        except ValueError: pass
    return True

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

    page.goto(url, timeout=15000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    html = page.content()
    print(f"HTML len: {len(html)}")

    title = ""
    h1 = page.query_selector("h1")
    if h1: title = strip(get_text(h1))
    print(f"title: {title[:80]}")

    artist = ""
    for sel in ["[class*='byline']",".author"]:
        try:
            el = page.query_selector(sel)
            if el: artist = strip(get_text(el)); break
        except: pass
    print(f"artist: {artist[:80]}")

    date_text = ""
    for sel in ["time[datetime]"]:
        try:
            el = page.query_selector(sel)
            if el: date_text = el.get_attribute("datetime") or ""; break
        except: pass
    print(f"date_text raw: '{date_text}'")
    in_win = in_window(date_text)
    print(f"in_window: {in_win} (CUTOFF={CUTOFF.date()})")

    excerpt = ""
    for sel in ["[class*='lede']","[class*='lead']"]:
        try:
            el = page.query_selector(sel)
            if el:
                t = strip(get_text(el))
                print(f"Excerpt sel={sel}: len={len(t)}, text={t[:100]}")
                if t and len(t) < 500:
                    excerpt = t
                break
        except: pass

    item_type = "review"
    html_l = html.lower()
    if any(k in html_l for k in ['interview','feature','profile']):
        item_type = "feature"
    print(f"item_type: {item_type}")

    # Non-music
    combined = f"{title} {artist}"
    nm = NON_MUSIC.search(combined)
    print(f"non-music match: {nm}")

    if nm:
        print("WOULD SKIP: non-music")
    elif not in_win:
        print("WOULD SKIP: outside window")
    else:
        print("WOULD ADD ITEM")

    browser.close()