#!/usr/bin/env python3
"""Scrape All About Jazz via playwright (chromium)."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_FILE = Path("/home/liyifan/music-record/2026/05/2026-05-24/all_about_jazz_reviews.json")
CUTOFF = datetime.now(timezone.utc) - timedelta(days=3)
EXCERPT_MAX = 500
SKIP_PATTERNS = [re.compile(r'\(BLU-RAY\)', re.I),
                 re.compile(r'\(UHD\)', re.I),
                 re.compile(r'\(VOD\)', re.I),
                 re.compile(r'\(DVD\)', re.I)]

def parse_date(date_str):
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def should_skip(title):
    for pat in SKIP_PATTERNS:
        if pat.search(title):
            return True
    return False

def extract_artist_from_body(body_text, title):
    """Extract artist from card body text after removing the title."""
    text = body_text.replace(title, "").strip()
    text = re.sub(r'^[\s\n\-–]+', '', text)
    text = re.sub(r'[\s\n]+', ' ', text)
    # Remove trailing LISTEN/BUY/etc
    text = re.sub(r'\s*(LISTEN|BUY|STREAM)\s*$', '', text, flags=re.I)
    text = text.strip()
    # Remove "From X" or "by Y" prefix
    text = re.sub(r'^(From\s+|by\s+)', '', text, flags=re.I)
    return text

def fix_url(url):
    if url and not url.startswith("http"):
        if url.startswith("//"):
            return "https:" + url
        elif url.startswith("/"):
            return "https://www.allaboutjazz.com" + url
        else:
            return "https://www.allaboutjazz.com/" + url
    return url

def get_reviews_from_page(page):
    """Extract review cards from the reviews page."""
    results = []

    cards = page.query_selector_all("div.card, div.thumb-card")

    for card in cards:
        try:
            # Get heading (h4 or h5 has album title)
            heading = card.query_selector("h4, h5")
            if not heading:
                continue
            title = heading.inner_text().strip()
            if not title or should_skip(title):
                continue

            # Get URL from heading link
            link = heading.query_selector("a")
            url = ""
            if link:
                url = link.get_attribute("href") or ""
            url = fix_url(url)
            if not url:
                continue

            # Get body text for artist info
            body_el = card.query_selector(".card-body")
            body_text = body_el.inner_text().strip() if body_el else ""
            artist = extract_artist_from_body(body_text, title)

            # Score - look for it
            score = None
            score_el = card.query_selector(".score, .rating")
            if score_el:
                sm = re.search(r'[\d.]+', score_el.inner_text())
                if sm:
                    score = float(sm.group())

            # Excerpt - text content, stripped, remove newlines
            excerpt = ""
            if body_text:
                excerpt = re.sub(r'\s+', ' ', body_text).strip()
            if len(excerpt) > EXCERPT_MAX:
                excerpt = excerpt[:EXCERPT_MAX] + "..."

            # Type - determine from URL pattern
            item_type = "review"
            if "/album/" in url:
                item_type = "review"
            elif "/media/track-" in url:
                item_type = "tracklist"
            elif "/musicians/" in url or "/articles/" in url:
                item_type = "feature"
            else:
                item_type = "review"

            results.append({
                "album": title,
                "artist": artist,
                "score": score,
                "url": url,
                "source": "allaboutjazz.com",
                "pub_date": "",
                "tags": [],
                "excerpt": excerpt,
                "site_id": "allaboutjazz",
                "crawl_status": "success",
                "type": item_type
            })
        except Exception:
            continue
    return results

def main():
    from playwright.sync_api import sync_playwright

    all_items = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20000)

        print("Navigating to allaboutjazz.com/reviews/...")
        try:
            page.goto("https://www.allaboutjazz.com/reviews/", timeout=20000)
        except Exception as e:
            print(f"Navigation failed: {e}")
            browser.close()
            with open(OUT_FILE, "w") as f:
                json.dump([], f)
            return

        page.wait_for_timeout(3000)

        try:
            page.get_by_text("Accept").click()
            page.wait_for_timeout(1000)
        except Exception:
            pass

        for page_num in range(2):
            print(f"\nScraping reviews page {page_num + 1}...")
            items = get_reviews_from_page(page)
            print(f"  Extracted {len(items)} items")
            for item in items:
                all_items.append(item)

            if page_num < 1:
                next_btn = page.query_selector("button#next_reviews")
                if next_btn:
                    disabled = next_btn.get_attribute("disabled")
                    if disabled:
                        print("  Next button disabled, stopping")
                        break
                    print("  Clicking next button...")
                    try:
                        next_btn.click()
                        page.wait_for_timeout(2500)
                    except Exception as e:
                        print(f"  Could not go next: {e}")
                        break
                else:
                    break

        browser.close()

    # Deduplicate by URL
    seen = set()
    filtered = []
    for item in all_items:
        if item["url"] and item["url"] not in seen:
            seen.add(item["url"])
            filtered.append(item)

    print(f"\nTotal unique items: {len(filtered)}")
    for item in filtered:
        score_str = f'(score: {item["score"]})' if item["score"] else ""
        print(f"  [{item['pub_date']}] {item['type']}: {item['album']} - {item['artist']} {score_str}")
        print(f"    url: {item['url']}")

    with open(OUT_FILE, "w") as f:
        json.dump(filtered, f, indent=2)
    print(f"\nWrote {len(filtered)} items to {OUT_FILE}")

if __name__ == "__main__":
    main()