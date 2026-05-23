#!/usr/bin/env python3
"""
DownBeat scraper using Playwright Chromium.
"""
import json
import re
import traceback
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

CUTOFF_DAYS = 3
OUTPUT_PATH = "/home/liyifan/music-record/2026/05/2026-05-24/downbeat_reviews.json"
SITE_ID = "downbeat"
MAX_PAGES = 2
NON_MUSIC_PATTERNS = [
    re.compile(r'\(BLU-RAY\)', re.I),
    re.compile(r'\(UHD\)', re.I),
    re.compile(r'\(VOD\)', re.I),
    re.compile(r'\(DVD\)', re.I),
]

def is_recent(pub_date_str):
    try:
        pub = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
    except Exception:
        return False
    now = datetime.now(timezone.utc)
    return (now - pub.replace(tzinfo=timezone.utc)).total_seconds() < CUTOFF_DAYS * 86400

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def looks_music(text):
    if not text:
        return True
    for p in NON_MUSIC_PATTERNS:
        if p.search(text):
            return False
    return True

def get_text(el):
    try:
        return el.inner_text()
    except Exception:
        try:
            return el.text_content() or ""
        except Exception:
            return ""

def parse_star_score(html):
    """Parse DownBeat's star rating: full stars + half stars. Max 5.0."""
    full = len(re.findall(r'fa-star"></i>', html))
    half = len(re.findall(r'fa-star-half"></i>', html))
    return full + half * 0.5

def parse_published_date(html):
    """Parse 'Published MONTH YEAR' from article HTML."""
    m = re.search(r'Published\s+(\w+)\s+(\d{4})', html, re.I)
    if m:
        month_str, year = m.group(1), m.group(2)
        month_map = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }
        month = month_map.get(month_str.title(), 1)
        return f"{year}-{month:02d}-01"
    return ""

def main():
    results = []
    seen_urls = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"
            )

            page = context.new_page()
            print("[INFO] Navigating to https://downbeat.com/reviews ...")
            try:
                resp = page.goto("https://downbeat.com/reviews", timeout=30000, wait_until="domcontentloaded")
                print(f"[INFO] Status: {resp.status if resp else 'none'}")
            except Exception as e:
                print(f"[WARN] Navigation (domcontentloaded) failed, trying commit: {e}")
                try:
                    resp = page.goto("https://downbeat.com/reviews", timeout=15000, wait_until="commit")
                    print(f"[INFO] Commit navigation succeeded")
                except Exception as e2:
                    print(f"[ERROR] All navigation attempts failed: {e2}")
                    with open(OUTPUT_PATH, "w") as f:
                        json.dump([], f)
                    browser.close()
                    return

            page.wait_for_timeout(3000)

            for selector in [
                "button:has-text('Accept')",
                "button:has-text('Agree')",
                "[aria-label*='Accept']",
                ".cookie-accept",
                "#didomi-host button",
            ]:
                try:
                    btn = page.query_selector(selector)
                    if btn and btn.is_visible():
                        btn.click()
                        print(f"[INFO] Clicked cookie: {selector}")
                        page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass

            all_links = []

            def collect_links():
                for a in page.query_selector_all("a[href*='/reviews/detail/']"):
                    href = a.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = "https://downbeat.com" + href
                        all_links.append(href)

            collect_links()
            print(f"[INFO] Found {len(all_links)} article links on page 1")

            if MAX_PAGES >= 2:
                for sel in ["a[href*='/reviews/P11']", "a:has-text('2')"]:
                    try:
                        next_btn = page.query_selector(sel)
                        if next_btn and next_btn.is_visible():
                            href = next_btn.get_attribute("href")
                            if href and '/reviews/P11' in href:
                                print(f"[INFO] Going to page 2...")
                                page.goto(href, timeout=15000, wait_until="domcontentloaded")
                                page.wait_for_timeout(2000)
                                collect_links()
                                print(f"[INFO] Total links after page 2: {len(all_links)}")
                                break
                    except Exception as e:
                        print(f"[WARN] Page 2: {e}")

            all_links = list(dict.fromkeys(all_links))
            print(f"[INFO] Deduplicated to {len(all_links)} links")

            for i, url in enumerate(all_links):
                print(f"\n[{i+1}/{len(all_links)}] {url}")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                article = None
                try:
                    article = context.new_page()
                    resp = article.goto(url, timeout=15000, wait_until="domcontentloaded")
                    article.wait_for_timeout(2000)

                    if resp and resp.status in [403, 503, 502, 500]:
                        print(f"  -> HTTP {resp.status} - blocked, returning []")
                        with open(OUTPUT_PATH, "w") as f:
                            json.dump([], f)
                        browser.close()
                        return

                    html = article.content()
                    if len(html) < 5000:
                        print(f"  -> Thin page ({len(html)} chars) - likely paywall")
                        article.close()
                        continue

                    album = ""
                    artist = ""
                    score = None
                    tags = []
                    excerpt = ""
                    review_type = "review"

                    h1 = article.query_selector("h1")
                    title = strip_html(get_text(h1)) if h1 else ""

                    h2 = article.query_selector("h2")
                    if h2:
                        artist = strip_html(get_text(h2))

                    subhead = article.query_selector("subhead")
                    if subhead:
                        album = strip_html(get_text(subhead))

                    if not artist:
                        m = re.search(r'<h2[^>]*>([^<]+)</h2>', html, re.I)
                        if m:
                            artist = strip_html(m.group(1))
                    if not album:
                        m = re.search(r'<subhead[^>]*>([^<]+)</subhead>', html, re.I)
                        if m:
                            album = strip_html(m.group(1))

                    score = parse_star_score(html)

                    # Parse Published date from article
                    pub_date = parse_published_date(html)

                    if not is_recent(pub_date):
                        print(f"  -> Outside 3-day window: {pub_date}")
                        article.close()
                        continue

                    if score == 0:
                        html_lower = html.lower()
                        feature_indicators = ["interview", "feature", "profile", "q&a", "conversation", "roundtable"]
                        if any(ind in html_lower for ind in feature_indicators):
                            review_type = "feature"

                    combined = f"{title} {album} {artist}"
                    if not looks_music(combined):
                        print(f"  -> Non-music item: {title[:60]}")
                        article.close()
                        continue

                    body_sel = ".article-body, .review-body, article, .entry-content"
                    body_el = article.query_selector(body_sel)
                    if body_el:
                        for p_el in body_el.query_selector_all("p"):
                            txt = strip_html(get_text(p_el))
                            if len(txt) > 50:
                                excerpt = txt
                                break

                    if not excerpt:
                        m = re.search(r'<p[^>]*>(.{100,500}?)</p>', html, re.I)
                        if m:
                            excerpt = strip_html(m.group(1))

                    item = {
                        "album": album,
                        "artist": artist,
                        "score": score if score > 0 else None,
                        "url": url,
                        "source": "downbeat.com",
                        "pub_date": pub_date,
                        "tags": tags,
                        "excerpt": excerpt[:500] if excerpt else "",
                        "site_id": SITE_ID,
                        "crawl_status": "success",
                        "type": review_type,
                    }
                    results.append(item)
                    print(f"  -> Added: {album}/{artist} | stars={score} | type={review_type} | date={pub_date}")

                    article.close()
                    article = None

                except Exception as e:
                    print(f"  -> ERROR: {e}")
                    if article:
                        try:
                            article.close()
                        except Exception:
                            pass
                    continue

            browser.close()

    except Exception as e:
        print(f"[FATAL] {e}")
        traceback.print_exc()
        with open(OUTPUT_PATH, "w") as f:
            json.dump([], f)
        return

    print(f"\n[DONE] Scraped {len(results)} items from DownBeat")
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[OUTPUT] Written to {OUTPUT_PATH}")
    for r in results:
        print(f"  [{r['type']}] {r.get('album','?')} / {r.get('artist','?')} | stars={r['score']} | {r['pub_date']}")

if __name__ == "__main__":
    main()