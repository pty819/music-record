#!/usr/bin/env python3
"""Scrape Truth & Lies Music — free jazz, improvised, adventurous jazz"""

import json, re, sys, time
from datetime import datetime, timedelta

sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.11/site_packages')
from playwright.sync_api import sync_playwright

SITE = "truthandliesmusic"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-24/truth_and_lies_music_reviews.json"
CUTOFF_DAYS = 3
MAX_PAGES = 2

BLOCKLIST_RE = re.compile(r'(BLU-RAY|UHD|VOD|DVD)', re.IGNORECASE)
TODAY = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
CUTOFF = TODAY - timedelta(days=CUTOFF_DAYS)

def parse_date(date_str):
    if not date_str:
        return None
    s = date_str.strip()
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:500]

def scrape():
    items = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        page.goto("https://www.truthandliesmusic.com/magazine", timeout=15000)
        time.sleep(2)

        for page_num in range(1, MAX_PAGES + 1):
            articles = page.query_selector_all("article")

            for i, article in enumerate(articles):
                link_el = article.query_selector("a")
                if not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                title = link_el.inner_text().strip()

                if not href or "/magazine/" not in href or href in seen_urls:
                    continue
                if any(x in href for x in ["category/", "tag/", "offset", "#"]):
                    continue
                if not title or len(title) < 5:
                    continue
                if BLOCKLIST_RE.search(title):
                    continue

                seen_urls.add(href)
                full_url = href if href.startswith("http") else f"https://www.truthandliesmusic.com{href}"

                article_page = ctx.new_page()
                try:
                    article_page.goto(full_url, timeout=15000)
                except Exception:
                    article_page.close()
                    continue

                pub_date = ""
                try:
                    time_el = article_page.query_selector("time")
                    if time_el:
                        raw = time_el.get_attribute("datetime") or time_el.inner_text().strip()
                        if raw:
                            if "T" in raw:
                                raw = raw.split("T")[0]
                            dt = parse_date(raw)
                            if dt:
                                if dt < CUTOFF:
                                    article_page.close()
                                    continue
                                pub_date = dt.strftime("%Y-%m-%d")
                            else:
                                pub_date = raw
                except Exception:
                    pass

                # Score
                score = None
                try:
                    score_el = article_page.query_selector("[class*='score'], [class*='rating'], [class*='stars']")
                    if score_el:
                        m = re.search(r'([\d.]+)', score_el.inner_text())
                        if m:
                            score = float(m.group(1))
                except Exception:
                    pass

                # Excerpt
                excerpt = ""
                try:
                    content = article_page.query_selector("article")
                    if content:
                        excerpt = strip_html(content.inner_text())[:500]
                except Exception:
                    excerpt = strip_html(title)

                # Artist
                artist = ""
                try:
                    byline = article_page.query_selector("[class*='author'], [class*='byline'], [class*='name']")
                    if byline:
                        artist = byline.inner_text().strip()
                        artist = re.sub(r'^Words by\s+', '', artist, flags=re.I)
                except Exception:
                    pass

                # Type
                item_type = "review"
                if "premiere" in href.lower():
                    item_type = "feature"
                elif "interview" in href.lower():
                    item_type = "feature"
                elif "tracklist" in href.lower():
                    item_type = "tracklist"

                items.append({
                    "album": title,
                    "artist": artist,
                    "score": score,
                    "url": full_url,
                    "source": "Truth & Lies Music",
                    "pub_date": pub_date,
                    "tags": [],
                    "excerpt": excerpt,
                    "site_id": SITE,
                    "crawl_status": "success",
                    "type": item_type,
                })
                article_page.close()

            # Next page
            if page_num < MAX_PAGES:
                try:
                    older = page.get_by_role("link", name=re.compile("Older Posts", re.I))
                    if older.is_visible(timeout=3000):
                        older.click()
                        time.sleep(2)
                    else:
                        break
                except Exception:
                    break

        browser.close()

    # Dedupe
    unique = {}
    for item in items:
        unique[item["url"]] = item
    result = list(unique.values())
    result.sort(key=lambda x: x.get("pub_date", ""), reverse=True)

    print(f"Wrote {len(result)} items to {OUTPUT_FILE}", file=sys.stderr)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return len(result)

if __name__ == "__main__":
    count = scrape()
    print(json.dumps({"count": count, "site": SITE, "output": OUTPUT_FILE}))