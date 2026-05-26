#!/usr/bin/env python3
"""Mixmag Asia review scraper - Playwright headless."""
from playwright.sync_api import sync_playwright
from pathlib import Path
import json, re
from datetime import datetime, timedelta

WORKSPACE = Path("/home/liyifan/music-record/2026/05/2026-05-25")
OUTPUT = WORKSPACE / "mixmag_asia_reviews.json"
SITE_ID = "mixmag_asia"
SOURCE = "Mixmag Asia"
CUTOFF_DAYS = 3
MAX_PAGES = 2
BASE_URL = "https://mixmag.asia/music/reviews"
cutoff = datetime.now() - timedelta(days=CUTOFF_DAYS)
EXCLUDES = ["BLU-RAY", "UHD", "VOD", "DVD"]
EXCLUDE_RE = re.compile("|".join(EXCLUDES), re.IGNORECASE)

def check_cookie(page):
    for sel in ["#onetrust-accept-btn-handler", "[aria-label='Accept']", "button:has-text('Accept')"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(1000)
                print("  cookie accept clicked")
                break
        except Exception:
            pass

def parse_date(text):
    if not text:
        return None
    text = text.strip()
    for fmt in ["%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except Exception:
            pass
    try:
        return datetime.strptime(text, "%b %d").isoformat()
    except Exception:
        pass
    return None

def extract_card(el, page_url):
    try:
        link_el = el.locator("a[href*='/read/']").first
        href = link_el.get_attribute("href") or ""
    except Exception:
        return None

    if "/read/" not in href:
        return None

    try:
        title = el.locator("h2, h3, .story-block__headline").first.text_content(timeout=1000)
    except Exception:
        title = ""
    title = (title or "").strip()

    try:
        meta = el.locator(".story-block__deck, .story-block__subheading, [class*='meta']").first.text_content(timeout=1000) or ""
    except Exception:
        meta = ""

    date_text = ""
    try:
        date_text = el.locator("time, .story-block__date, [class*='date']").first.text_content(timeout=500) or ""
    except Exception:
        pass
    pub_date = parse_date(date_text)

    score = None
    try:
        score_text = el.locator("[class*='score'], [class*='rating'], .rating, .review-score").first.text_content(timeout=500) or ""
        m = re.search(r"(\d[\d.]*)\s*/\s*10", score_text)
        if m:
            score = float(m.group(1))
    except Exception:
        pass

    try:
        excerpt = el.locator(".story-block__deck, p, [class*='excerpt']").first.text_content(timeout=500) or ""
    except Exception:
        excerpt = ""
    excerpt = re.sub(r"<[^>]+>", "", excerpt).strip()[:500]

    album = title
    artist = meta.strip()
    url = href if href.startswith("http") else f"https://mixmag.asia{href}"

    return {
        "album": album,
        "artist": artist,
        "score": score,
        "url": url,
        "source": SOURCE,
        "pub_date": pub_date,
        "tags": [],
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "ok",
        "type": "review",
    }

def is_excluded(item):
    text = (item.get("album") or "") + (item.get("excerpt") or "")
    return bool(EXCLUDE_RE.search(text))

def main():
    results = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20000)

        for page_num in range(1, MAX_PAGES + 1):
            url = BASE_URL if page_num == 1 else f"{BASE_URL}?page={page_num}"
            print(f"[page {page_num}] {url}")
            resp = page.goto(url, timeout=20000)
            print(f"  status: {resp.status}")
            page.wait_for_timeout(2000)
            check_cookie(page)
            page.wait_for_timeout(1000)

            articles = page.locator("article.story-block")
            n = articles.count()
            print(f"  found {n} article blocks")

            page_break = False
            for i in range(n):
                el = articles.nth(i)
                item = extract_card(el, url)
                if not item:
                    continue

                if item["url"] in seen:
                    continue
                seen.add(item["url"])

                if item["pub_date"]:
                    try:
                        pub = datetime.fromisoformat(item["pub_date"])
                        if pub < cutoff:
                            print(f"  [date filter] cutoff hit at '{item['pub_date']}', stopping")
                            page_break = True
                            break
                    except Exception:
                        pass

                if is_excluded(item):
                    print(f"  [exclude] {item['album'][:50]}")
                else:
                    results.append(item)
                    print(f"  [+] {item['album'][:60]}")

            if page_break:
                break

            if n == 0:
                print("  no articles found, stopping")
                break

        browser.close()

    print(f"\nTotal: {len(results)}")
    with open(OUTPUT, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}")
    return results

if __name__ == "__main__":
    main()