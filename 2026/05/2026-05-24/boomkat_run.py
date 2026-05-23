#!/usr/bin/env python3
import subprocess
import sys
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

CUTOFF_DAYS = 3
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=CUTOFF_DAYS)
OUT = "/home/liyifan/music-record/2026/05/2026-05-24/boomkat_reviews.json"
SITE = "boomkat"

def parse_date(date_str):
    # Boomkat dates like "May 21, 2026"
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

def build_script():
    code = f"""
import sys
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.11/site-packages')

from camoufox import Camoufox

results = []

with Camoufox(headless=True) as browser:
    page = browser.new_page()
    page.set_viewport_size({{"width": 1280, "height": 800}})

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
                    print(f"Clicked cookie button: {{selector}}")
                    break
            except Exception:
                pass
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f"Cookie handling: {{e}}")

    # Scrape 2 pages of listing
    for page_num in range(1, 3):
        url = f"https://boomkat.com/in-writing?page={{page_num}}"
        print(f"Loading: {{url}}")
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Page load failed: {{e}}")
            break

        # Each review item
        items = page.locator("article").all()
        if not items:
            print(f"No articles found on page {{page_num}}")
            break

        for item in items:
            try:
                # Title/album
                title_el = item.locator("h2, h3").first
                album = title_el.inner_text().strip() if title_el.is_visible() else None

                if is_non_music(album):
                    print(f"SKIP non-music: {{album}}")
                    continue

                # Artist
                artist_el = item.locator(".artist, .author, [class*='artist']").first
                artist = artist_el.inner_text().strip() if artist_el.is_visible() else None

                # Score
                score = None
                try:
                    score_el = item.locator("[class*='score'], [class*='rating']").first
                    txt = score_el.inner_text().strip()
                    m = re.search(r'(\\d+)', txt)
                    if m:
                        score = int(m.group(1))
                except Exception:
                    pass

                # URL
                link_el = item.locator("a").first
                article_url = link_el.get_attribute("href") if link_el.is_visible() else None
                if article_url:
                    article_url = urljoin("https://boomkat.com", article_url)

                # Date
                date_el = item.locator("time, [class*='date'], [class*='pub']").first
                date_str = date_el.inner_text().strip() if date_el.is_visible() else None
                pub_date = parse_date(date_str) if date_str else None

                if pub_date and is_too_old(pub_date):
                    print(f"STOP: too old {{pub_date}}")
                    break

                # Excerpt
                excerpt_el = item.locator("p, [class*='excerpt'], [class*='summary']").first
                excerpt = strip_html(excerpt_el.inner_text().strip()) if excerpt_el.is_visible() else None

                # Type
                article_type = "review"
                type_el = item.locator("[class*='type'], [class*='label']").first
                if type_el.is_visible():
                    t = type_el.inner_text().strip().lower()
                    if "feature" in t or "interview" in t:
                        article_type = "feature"
                        score = None

                results.append({{
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
                }})
                print(f"OK: {{album}} | {{artist}} | score={{score}}")
            except Exception as e:
                print(f"Item error: {{e}}")
                continue

        if pub_date and is_too_old(pub_date):
            break

import json
with open("{OUT}", "w") as f:
    json.dump(results, f, indent=2)
print(f"Saved {{len(results)}} items")
"""
    return code

# Write and execute via camoufox CLI
script_path = "/home/liyifan/music-record/2026/05/2026-05-24/boomkat_scraper.py"
with open(script_path, "w") as f:
    f.write(build_script())

print("Script written, running via camoufox...")
sys.stdout.flush()
sys.stderr.flush()