#!/usr/bin/env python3
"""Scrape JazzTimes - collect album/concert reviews from past 3 days."""
import json, re, sys, time, os
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

OUTPUT = "/home/liyifan/music-record/2026/05/2026-05-24/jazztimes_reviews.json"
PROGRESS = "/home/liyifan/music-record/2026/05/2026-05-24/.scrape_progress.json"
SITE = "jazztimes"
SITE_URL = "https://www.jazztimes.com"
DAYS = 3

NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=DAYS)
NON_MUSIC = re.compile(r'(BLU-RAY|UHD|VOD|DVD|BOOK)', re.IGNORECASE)
REVIEW_SECTIONS = re.compile(r'^/(reviews/live|reviews/albums|reviews/books)/', re.IGNORECASE)

def log(msg):
    print(msg, flush=True)

def parse_date(s):
    if not s: return None
    s = re.sub(r'\s+', ' ', s.strip())
    for fmt in ["%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%d",
                "%B %d, %Y","%b %d, %Y","%B %d %Y","%b %d %Y","%m/%d/%Y"]:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError: pass
    return None

def strip(t):
    if not t: return ""
    t = re.sub(r'<br\s*/?>', ' ', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:500]

def get_text(el):
    try: return el.inner_text()
    except: return el.text_content() or ""

UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0"

def collect_urls():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"], executable_path="/usr/bin/chromium")
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()
        try:
            page.goto(SITE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
        except Exception as e:
            log(f"Homepage error: {e}")
            browser.close()
            return []
        for sel in ["button:has-text('Accept')","button:has-text('Agree')"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click(); page.wait_for_timeout(1500); break
            except: pass
        try:
            page.wait_for_selector("article", timeout=5000)
        except: pass

        urls = []
        for a in page.query_selector_all("article a"):
            href = a.get_attribute("href")
            if not href: continue
            if href.startswith('/'): href = urljoin(SITE_URL, href)
            # Prefer review-section articles, accept blog/features too
            urls.append(href)

        urls = list(dict.fromkeys(urls))
        log(f"Collected {len(urls)} URLs")
        browser.close()
        return urls

def visit_one(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"], executable_path="/usr/bin/chromium")
            ctx = browser.new_context(user_agent=UA)
            page = ctx.new_page()
            try:
                resp = page.goto(url, timeout=15000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
            except Exception:
                try:
                    page.goto(url, timeout=10000, wait_until="commit")
                    page.wait_for_timeout(2000)
                except Exception:
                    browser.close()
                    return None
            if resp and resp.status in [403, 503, 502, 500]:
                browser.close()
                return None
            html = page.content()
            if len(html) < 5000:
                browser.close()
                return None

            title = strip(get_text(page.query_selector("h1"))) if page.query_selector("h1") else ""

            artist = ""
            for sel in ["[class*='byline']",".author","[class*='author']"]:
                try:
                    el = page.query_selector(sel)
                    if el: artist = strip(get_text(el)); break
                except: pass

            date_text = ""
            for sel in ["time[datetime]","[class*='date']",".post-date",".entry-date"]:
                try:
                    el = page.query_selector(sel)
                    if el: date_text = el.get_attribute("datetime") or strip(get_text(el)); break
                except: pass

            score = None
            for sel in ["[class*='score']","[class*='rating']","[itemprop='ratingValue']"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        m = re.search(r'([\d\.]+)', strip(get_text(el)))
                        if m: score = float(m.group(1)); break
                except: pass

            excerpt = ""
            for sel in ["[class*='lede']","[class*='lead']","[class*='summary']"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        t = strip(get_text(el))
                        if len(t) > 10: excerpt = t; break
                except: pass
            if not excerpt:
                try:
                    body = page.query_selector("article,[class*='body'],.content")
                    if body:
                        for p_el in body.query_selector_all("p"):
                            txt = strip(get_text(p_el))
                            if len(txt) > 50: excerpt = txt; break
                except: pass

            item_type = "review"
            path = url.split("jazztimes.com")[-1].lstrip('/')
            if REVIEW_SECTIONS.match("/" + path):
                item_type = "review"
            elif '/book' in path.lower():
                item_type = "review"
            else:
                item_type = "feature"

            # Date filter - skip if clearly outside window
            if date_text:
                parsed = parse_date(date_text)
                if parsed and parsed < CUTOFF:
                    browser.close()
                    return None

            browser.close()

            if NON_MUSIC.search(f"{title} {artist}"):
                return None

            return {"album": title, "artist": artist, "score": score, "url": url, "source": SITE,
                    "pub_date": date_text[:30], "tags": [], "excerpt": excerpt, "site_id": SITE,
                    "crawl_status": "success", "type": item_type}
    except Exception:
        return None

def save(items):
    with open(OUTPUT,"w") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    with open(PROGRESS,"w") as f:
        json.dump({"count": len(items), "saved_at": str(NOW)}, f)

def main():
    log("Collecting article URLs...")
    urls = collect_urls()
    if not urls:
        save([])
        print("SCRAPE_COMPLETE:0")
        return

    items = []
    for i, url in enumerate(urls):
        log(f"[{i+1}/{len(urls)}] {url[:80]}")
        item = visit_one(url)
        if item:
            items.append(item)
            log(f"  OK: {item['album'][:55]} | score={item['score']} | date={item['pub_date'][:19]}")
            if i > 0 and i % 5 == 0:
                save(items)  # checkpoint every 5 articles
        time.sleep(0.5)
        # Check elapsed time - stop if 180s elapsed
        # (rely on outer timeout for now)

    save(items)
    log(f"Done. {len(items)} items written.")
    print(f"SCRAPE_COMPLETE:{len(items)}")

if __name__ == "__main__":
    main()