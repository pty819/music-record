#!/usr/bin/env python3
"""Scrape Point of Departure (pointofdeparture.org) - 3-day window"""

import sys, re, json
sys.path.insert(0, '/usr/local/lib/python3/dist-packages')

from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

SITE = "point_of_departure"
TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
CUTOFF = TODAY - timedelta(days=3)
OUTPUT = "/home/liyifan/music-record/2026/05/2026-05-24/point_of_departure_reviews.json"
print(f"Cutoff: {CUTOFF.date()}")

BLOCKLIST_RE = re.compile(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', re.IGNORECASE)
SKIP_TYPES = {"tracklist"}

def is_within_window(date_str):
    try:
        # Try common formats
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y"):
            try:
                dt = datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
                return CUTOFF <= dt <= TODAY
            except ValueError:
                pass
        return None  # can't parse
    except Exception:
        return None

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def scrape():
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://pointofdeparture.org/", timeout=30000)
        page.wait_for_timeout(2000)

        # Handle cookie banner
        try:
            accept_btn = page.get_by_text("Accept").first
            accept_btn.click()
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # Get posts from listing pages (max 2)
        for page_num in range(1, 3):
            url = f"https://pointofdeparture.org/page/{page_num}/" if page_num > 1 else "https://pointofdeparture.org/"
            print(f"Scanning: {url}")
            page.goto(url, timeout=30000)
            page.wait_for_timeout(2000)

            articles = page.query_selector_all("article")
            print(f"  Found {len(articles)} articles on page {page_num}")
            if not articles:
                break

            for article in articles:
                try:
                    # Get link and title
                    link_el = article.query_selector("h2 a") or article.query_selector("h3 a") or article.query_selector("a")
                    if not link_el:
                        continue
                    title = strip_html(link_el.inner_text())
                    url_link = link_el.get_attribute("href")
                    if not url_link or title.strip() == "":
                        continue

                    # Try to get date
                    date_el = article.query_selector("time") or article.query_selector(".date") or article.query_selector("[class*='date']")
                    date_str = date_el.inner_text() if date_el else ""
                    in_window = is_within_window(date_str)
                    print(f"  -> '{title[:50]}' date={date_str!r} in_window={in_window}")

                    if in_window is None:
                        continue
                    if not in_window:
                        print(f"    OUTSIDE 3-day window, stopping page scan")
                        break

                    # Check blocklist
                    if BLOCKLIST_RE.search(title):
                        print(f"    SKIP (blocklist)")
                        continue

                    # Determine type
                    article_class = (article.get_attribute("class") or "").lower()
                    if "feature" in article_class or "interview" in article_class:
                        item_type = "feature"
                        score = None
                    elif "tracklist" in article_class:
                        item_type = "tracklist"
                        score = None
                    else:
                        item_type = "review"
                        # Try score
                        score_el = article.query_selector("[class*='score']") or article.query_selector(".rating")
                        score_text = score_el.inner_text() if score_el else ""
                        sc = re.search(r'([\d.]+)', score_text)
                        score = float(sc.group(1)) if sc else None

                    # Get artist/album
                    meta = article.inner_text()
                    artist = ""
                    album = title
                    if " - " in title:
                        parts = title.split(" - ", 1)
                        artist = parts[0].strip()
                        album = parts[1].strip()

                    results.append({
                        "album": album,
                        "artist": artist,
                        "score": score,
                        "url": url_link,
                        "source": "pointofdeparture.org",
                        "pub_date": date_str,
                        "tags": [],
                        "excerpt": title,
                        "site_id": SITE,
                        "crawl_status": "success",
                        "type": item_type
                    })
                    print(f"    OK: {item_type} '{title[:60]}'")

                except Exception as e:
                    print(f"  ERROR: {e}")
                    continue

        browser.close()

    # Deduplicate by URL
    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    print(f"\nTotal unique items: {len(unique)}")
    return unique

if __name__ == "__main__":
    items = scrape()
    with open(OUTPUT, "w") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"Written to {OUTPUT}")
    print(f"Items: {len(items)}")