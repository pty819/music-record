#!/usr/bin/env python3
"""Scrape Free Jazz Blog (www.freejazzblog.org)"""

import json, sys, re, time
from datetime import datetime, timedelta
from urllib.parse import urljoin

# ── config ──────────────────────────────────────────────────────────────
SITE = "free_jazz_blog"
URL  = "https://www.freejazzblog.org/"
OUT  = "/home/liyifan/music-record/2026/05/2026-05-24/free_jazz_blog_reviews.json"
DAYS = 3
MAX_PAGES = 2          # only first 2 list pages allowed
# ─────────────────────────────────────────────────────────────────────

def load_browser():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    return browser, pw

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:500]

def extract_date(text):
    """Parse e.g. 'May 21, 2026'"""
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return None

def within_days(date_str, days):
    if not date_str:
        return True   # don't filter out if unparseable
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        cutoff = datetime.now() - timedelta(days=days)
        return d >= cutoff
    except Exception:
        return True

# ── helpers to detect non-music ───────────────────────────────────────
NON_MUSIC_PATTERNS = [
    re.compile(r'\(BLU-RAY\)', re.IGNORECASE),
    re.compile(r'\(UHD\)', re.IGNORECASE),
    re.compile(r'\(VOD\)', re.IGNORECASE),
    re.compile(r'\(DVD\)', re.IGNORECASE),
]

def is_non_music(title):
    return any(p.search(title) for p in NON_MUSIC_PATTERNS)

# ─────────────────────────────────────────────────────────────────────
def scrape():
    print(f"[freejazzblog] Starting scrape — {URL}")
    browser, pw = load_browser()
    try:
        page = browser.new_page()

        # Handle cookie banner
        try:
            page.goto(URL, wait_until="domcontentloaded")
            time.sleep(1.5)
            for selector in ['text=Accept', 'text=Agree', 'text=OK', '#cookieConsent', '.cookie-accept']:
                try:
                    el = page.query_selector(selector)
                    if el:
                        el.click()
                        print("[freejazzblog] Accepted cookie banner")
                        time.sleep(0.5)
                        break
                except Exception:
                    pass
        except Exception as e:
            print(f"[freejazzblog] navigate error: {e}")

        items = []
        seen_urls = set()

        for page_num in range(1, MAX_PAGES + 1):
            print(f"[freejazzblog] Scraping list page {page_num}")
            try:
                page.goto(URL, wait_until="domcontentloaded")
                time.sleep(2)
            except Exception as e:
                print(f"[freejazzblog] page {page_num} load error: {e}")
                break

            article_links = set()
            try:
                for a in page.query_selector_all("a.post-title-link, a.post-title, h3.post-title a, .item-title a"):
                    href = a.get_attribute("href")
                    if href:
                        article_links.add(href)
                for h3 in page.query_selector_all("h3"):
                    a = h3.query_selector("a")
                    if a:
                        href = a.get_attribute("href")
                        if href:
                            article_links.add(href)
            except Exception as e:
                print(f"[freejazzblog] link extraction error: {e}")

            print(f"[freejazzblog] Found {len(article_links)} article links on page {page_num}")

            for article_url in article_links:
                if article_url in seen_urls:
                    continue
                seen_urls.add(article_url)

                try:
                    page.goto(article_url, wait_until="domcontentloaded")
                    time.sleep(1.5)
                except Exception as e:
                    print(f"[freejazzblog] article load error: {article_url} → {e}")
                    continue

                try:
                    title_el = page.query_selector("h3.post-title, h1.post-title, .post-title")
                    title = title_el.inner_text().strip() if title_el else "Unknown"
                except Exception:
                    title = "Unknown"

                if is_non_music(title):
                    print(f"[freejazzblog] SKIP (non-music): {title}")
                    continue

                date_str = None
                try:
                    for sel in ["time[itemprop='datePublished']", ".post-timestamp", ".post-date"]:
                        el = page.query_selector(sel)
                        if el:
                            date_str = extract_date(el.inner_text().strip())
                            if date_str:
                                break
                except Exception:
                    pass

                if date_str and not within_days(date_str, DAYS):
                    print(f"[freejazzblog] SKIP (too old): {title} [{date_str}]")
                    continue

                score = None
                try:
                    score_el = page.query_selector(".rating, .score, [class*='rating'], [class*='score']")
                    if score_el:
                        score_text = score_el.inner_text().strip()
                        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:/\s*\d+)?', score_text)
                        if m:
                            score = float(m.group(1))
                except Exception:
                    pass

                excerpt = ""
                try:
                    for p in page.query_selector_all(".post-body p, .post-content p, article p"):
                        txt = p.inner_text().strip()
                        if len(txt) > 50:
                            excerpt = strip_html(txt)
                            break
                except Exception:
                    pass

                artist = "Unknown"
                album = title
                if " - " in title:
                    parts = title.split(" - ", 1)
                    artist = parts[0].strip()
                    album = parts[1].strip()

                page_text = page.evaluate("() => document.body.innerText")
                ltype = "review"
                if any(k in page_text.lower() for k in ["interview", "feature", "profile", "spotlight"]):
                    ltype = "feature"

                item = {
                    "album": album,
                    "artist": artist,
                    "score": score,
                    "url": article_url,
                    "source": "freejazzblog.org",
                    "pub_date": date_str or "",
                    "tags": [],
                    "excerpt": excerpt,
                    "site_id": SITE,
                    "crawl_status": "success",
                    "type": ltype,
                }
                items.append(item)
                print(f"[freejazzblog] ✓ {artist} - {album}")

            print(f"[freejazzblog] Page {page_num} done, total items: {len(items)}")

    finally:
        browser.close()
        pw.stop()

    print(f"[freejazzblog] Total items collected: {len(items)}")

    with open(OUT, "w") as f:
        json.dump(items, f, indent=2)
    print(f"[freejazzblog] Written to {OUT}")

    return items

if __name__ == "__main__":
    items = scrape()
    print(f"Done: {len(items)} items")