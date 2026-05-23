#!/usr/bin/env python3
"""Scrape Sequenza21 — browser approach (RSS had no fresh items)."""
import sys, re, json
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

SITE_URL = "https://www.sequenza21.com/"
OUTPUT   = "/home/liyifan/music-record/2026/05/2026-05-24/sequenza21_reviews.json"
CUTOFF   = datetime.now() - timedelta(days=3)
SITE_ID  = "sequenza21"

def log(msg):
    print(msg, flush=True)

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:500]

def parse_date(date_str):
    """Parse ISO date like 2026-05-20T20:37:27-04:00"""
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
    except:
        return datetime.now()

results = []
seen_urls = set()

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()

    resp = page.goto(SITE_URL, timeout=15000, wait_until="load")
    log(f"Status: {resp.status}")
    page.wait_for_timeout(3000)

    # Cookie consent
    for text in ["Accept", "Agree", "Consent"]:
        try:
            btn = page.locator(f"text={text}").first
            if btn.is_visible():
                btn.click()
                log("Clicked cookie Accept")
                page.wait_for_timeout(1000)
                break
        except:
            pass

    # Scan up to 2 listing pages
    for page_num in range(1, 3):
        log(f"\n=== Page {page_num} ===")

        articles = page.query_selector_all("article")
        log(f"Found {len(articles)} <article> elements")

        for article in articles:
            try:
                # Get the main article link (skip category links)
                all_links = article.query_selector_all("a[href]")
                url = ""
                title_text = ""
                for link in all_links:
                    href = link.get_attribute("href") or ""
                    txt = link.inner_text().strip()
                    # The main article link goes to a /YYYY/MM/... path with the article title
                    if "/202" in href and "sequenza21.com" in href and len(txt) > 5:
                        url = href
                        title_text = txt
                        break

                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                # Title from h2/h3 inside article
                h_el = article.query_selector("h2, h3")
                title = h_el.inner_text().strip() if h_el else title_text

                if not title or len(title) < 3:
                    continue

                # Date from <time> element
                time_el = article.query_selector("time")
                date_str = time_el.get_attribute("datetime") if time_el else ""
                pub_date = parse_date(date_str) if date_str else datetime.now()

                if pub_date < CUTOFF:
                    log(f"  SKIP (old {pub_date.strftime('%Y-%m-%d')}): {title[:50]}")
                    continue

                # Non-music filter
                if any(x in title.lower() for x in ["blu-ray", "uhd", "vod", "dvd"]):
                    log(f"  SKIP (non-music): {title}")
                    continue

                # Artist / album from "Artist - Album" format
                album = title
                artist = ""
                if " - " in title:
                    parts = title.split(" - ", 1)
                    artist = parts[0].strip()
                    album = parts[1].strip()

                # Excerpt from paragraph
                ex_el = article.query_selector("p")
                excerpt = strip_html(ex_el.inner_text()) if ex_el else album

                # Categories as tags
                cats = []
                for cat_el in article.query_selector_all("[class*='cat'], .categories, [class*='tag']"):
                    cat_text = cat_el.inner_text().strip().replace("\n", ", ")
                    if cat_text:
                        cats.append(cat_text)

                cat_str = " ".join(cats).lower()
                if any(x in cat_str for x in ["feature", "interview", "profile"]):
                    item_type = "feature"
                elif any(x in cat_str for x in ["tracklist"]):
                    item_type = "tracklist"
                else:
                    item_type = "review"

                results.append({
                    "album": album,
                    "artist": artist,
                    "score": None,
                    "url": url,
                    "source": SITE_URL,
                    "pub_date": pub_date.strftime("%Y-%m-%d"),
                    "tags": cats,
                    "excerpt": excerpt[:500],
                    "site_id": SITE_ID,
                    "crawl_status": "success",
                    "type": item_type,
                })
                log(f"  OK [{item_type}] {pub_date.strftime('%Y-%m-%d')} {artist} - {album[:50]}")

            except Exception as e:
                log(f"  Error: {e}")

        # Navigate to older posts if on page 1
        if page_num == 1:
            older_link = None
            all_links = page.query_selector_all("a")
            for link in all_links:
                text = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                if any(x in text for x in ["Older Posts", "Older", "Next", "»", ">>"]) and href:
                    older_link = href
                    log(f"Found nav link: '{text}' -> {href}")
                    break

            if older_link:
                page.goto(older_link, timeout=15000, wait_until="load")
                page.wait_for_timeout(2000)
            else:
                log("No older posts link found, stopping")
                break

    browser.close()

with open(OUTPUT, "w") as f:
    json.dump(results, f, indent=2)

log(f"\nDone: {len(results)} items")
print(json.dumps({"count": len(results), "output": OUTPUT}))