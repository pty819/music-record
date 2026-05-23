#!/usr/bin/env python3
import sys
import re
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

sys.path.insert(0, '/home/liyifan/.hermes/hermes-agent/venv/lib/python3.11/site-packages')

from playwright.sync_api import sync_playwright

CUTOFF_DAYS = 3
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=CUTOFF_DAYS)
OUT = "/home/liyifan/music-record/2026/05/2026-05-24/boomkat_reviews.json"
SITE = "boomkat"

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def strip_html(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def is_too_old(pub_date):
    if pub_date is None:
        return False
    return pub_date < CUTOFF

def is_non_music(album):
    if not album:
        return False
    text = album.lower()
    return any(k in text for k in ["(blu-ray)", "(uhd)", "(vod)", "(dvd)"])

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    # Cookie wall
    page.goto("https://boomkat.com/", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    try:
        for selector in [
            "button[aria-label*='Accept']",
            "button[aria-label*='Agree']",
            "text=Accept",
            "text=Agree",
            "text=OK",
            "#onetrust-accept-btn-handler",
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    el.click()
                    print(f"Clicked: {selector}")
                    break
            except Exception:
                pass
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f"Cookie: {e}")

    # Scrape 2 pages
    for page_num in range(1, 3):
        url = f"https://boomkat.com/in-writing?page={page_num}"
        print(f"Loading: {url}")
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Load failed: {e}")
            break

        items = page.locator("article").all()
        if not items:
            print(f"No articles page {page_num}")
            break

        for item in items:
            try:
                # Title
                title_el = item.locator("h2, h3").first
                album = title_el.inner_text().strip() if title_el.is_visible() else None

                if is_non_music(album):
                    print(f"SKIP non-music: {album}")
                    continue

                # Artist
                artist = None
                for cls in [".artist", "[class*='artist']", "[class*='author']"]:
                    try:
                        el = item.locator(cls).first
                        if el.is_visible():
                            artist = el.inner_text().strip()
                            break
                    except Exception:
                        pass

                # Score
                score = None
                try:
                    for cls in ["[class*='score']", "[class*='rating']", "[class*='number']"]:
                        el = item.locator(cls).first
                        if el.is_visible():
                            txt = el.inner_text()
                            m = re.search(r'(\d+)', txt)
                            if m:
                                score = int(m.group(1))
                                break
                except Exception:
                    pass

                # URL
                link_el = item.locator("a").first
                article_url = link_el.get_attribute("href") if link_el.is_visible() else None
                if article_url and not article_url.startswith("http"):
                    article_url = urljoin("https://boomkat.com", article_url)

                # Date
                pub_date = None
                for sel in ["time", "[class*='date']", "[class*='pub']"]:
                    try:
                        el = item.locator(sel).first
                        if el.is_visible():
                            txt = el.inner_text().strip()
                            pub_date = parse_date(txt)
                            if pub_date:
                                break
                    except Exception:
                        pass

                if pub_date and is_too_old(pub_date):
                    print(f"STOP: too old {pub_date}")
                    break

                # Excerpt
                excerpt = None
                for sel in ["p", "[class*='excerpt']", "[class*='summary']"]:
                    try:
                        el = item.locator(sel).first
                        if el.is_visible():
                            excerpt = strip_html(el.inner_text())
                            break
                    except Exception:
                        pass

                # Type
                article_type = "review"
                try:
                    for cls in ["[class*='type']", "[class*='label']", "[class*='tag']"]:
                        el = item.locator(cls).first
                        if el.is_visible():
                            t = el.inner_text().lower()
                            if "feature" in t or "interview" in t:
                                article_type = "feature"
                                score = None
                            break
                except Exception:
                    pass

                results.append({
                    "album": album,
                    "artist": artist,
                    "score": score,
                    "url": article_url,
                    "source": "boomkat.com",
                    "pub_date": pub_date.isoformat() if pub_date else None,
                    "tags": [],
                    "excerpt": excerpt,
                    "site_id": "boomkat",
                    "crawl_status": "success",
                    "type": article_type,
                })
                print(f"OK: {album} | {artist} | score={score}")
            except Exception as e:
                print(f"Item error: {e}")
                continue

        if pub_date and is_too_old(pub_date):
            break

    browser.close()

with open(OUT, "w") as f:
    json.dump(results, f, indent=2)
print(f"Saved {len(results)} items to {OUT}")