#!/usr/bin/env python3
"""
Scrape ProgressoR (www.progressor.net) via browser with http:// fallback.
"""
import json, re, time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

SITE = "progressor.net"
OUTPUT = "/home/liyifan/music-record/2026/05/2026-05-25/progressor_reviews.json"
DAYS_CUTOFF = 3
TODAY = datetime.now(timezone.utc)
CUTOFF_DATE = TODAY - timedelta(days=DAYS_CUTOFF)
RESULTS = []

def log(msg):
    print(f"[ProgressoR] {msg}", flush=True)

def is_within_window(pub_date_str):
    if not pub_date_str:
        return True
    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%B %d, %Y"]:
        try:
            dt = datetime.strptime(pub_date_str.strip(), fmt).replace(tzinfo=timezone.utc)
            return dt >= CUTOFF_DATE
        except ValueError:
            pass
    return True

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def score_from_text(text):
    if not text:
        return None
    text = text.strip()
    m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*100', text)
    if m:
        return float(m.group(1))
    m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', text)
    if m:
        return float(m.group(1)) * 10
    stars = text.count('★') + text.count('*')
    if 0 < stars <= 5:
        return stars * 20
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if m:
        return float(m.group(1))
    return None

def parse_article_page(page):
    """Parse a single review article page for album/artist/score/excerpt."""
    result = {}

    # Title usually in h1 or .title
    title_el = page.query_selector('h1, h2, .title, .entry-title, [class*="title"]')
    title_text = strip_html(title_el.inner_text()) if title_el else ""

    # Artist-album format: "Artist - Album"
    if ' - ' in title_text:
        parts = title_text.split(' - ', 1)
        result['artist'] = parts[0].strip()
        result['album'] = parts[1].strip()
    else:
        result['album'] = title_text
        result['artist'] = ""

    # Score
    score_el = page.query_selector('.score, .rating, [class*="score"], .wppr-rating')
    if score_el:
        result['score'] = score_from_text(score_el.inner_text())
    else:
        result['score'] = None

    # Date
    date_el = page.query_selector('time, .date, .posted, .meta')
    result['pub_date'] = strip_html(date_el.inner_text()) if date_el else ""

    # Excerpt - first paragraph of body
    body_el = page.query_selector('.entry-content p, .review-body p, .content p, p')
    result['excerpt'] = strip_html(body_el.inner_text()) if body_el else ""

    # Type
    url = page.url
    if any(k in url.lower() for k in ['interview', 'feature', 'premiere']):
        result['type'] = 'feature'
        result['score'] = None
    elif 'tracklist' in url.lower():
        result['type'] = 'tracklist'
    else:
        result['type'] = 'review'

    return result

def scrape_listing(page, url):
    """Scrape a listing page and return list of article URLs."""
    log(f"Scraping listing: {url}")
    try:
        page.goto(url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        log(f"Error loading {url}: {e}")
        return []

    article_urls = []

    # Find all links that look like article/review pages
    all_links = page.query_selector_all('a[href]')
    for link in all_links:
        try:
            href = link.get_attribute('href')
            text = strip_html(link.inner_text()).lower()
            if not href:
                continue
            # Skip navigation, non-review links
            skip_patterns = ['article', 'genre', 'label', 'interview', 'contact',
                           'vestnik', 'archive', 'bandlist', 'list/', 'index',
                           'whatisprog', 'musea', 'cathedral', '.css', '.js',
                           'facebook', 'twitter', 'youtube']
            if any(p in href.lower() for p in skip_patterns) and 'review' not in href.lower():
                continue
            # Look for review URLs
            if 'review' in href.lower() or 'cd_ ' in text or 'mp3' in text:
                if href.startswith('http'):
                    article_urls.append(href)
                else:
                    article_urls.append(f"http://www.progressor.net/{href.lstrip('/')}")
        except Exception:
            continue

    # Dedupe
    article_urls = list(dict.fromkeys(article_urls))
    log(f"  Found {len(article_urls)} article URLs")
    return article_urls[:20]  # limit to first 20

def scrape_review_detail(page, url):
    """Visit a review article page and scrape it."""
    log(f"  Scraping: {url}")
    try:
        page.goto(url, timeout=30000)
        time.sleep(1)
    except Exception as e:
        log(f"  Error loading {url}: {e}")
        return None

    data = parse_article_page(page)
    data['url'] = url
    data['source'] = SITE
    data['site_id'] = 'progressor'
    data['tags'] = []

    # Check date
    if not is_within_window(data['pub_date']) and data['pub_date']:
        log(f"  SKIP (outside window): {data['pub_date']}")
        return None

    # Non-music filter
    if any(k in data['album'].upper() for k in ['BLU-RAY', 'UHD', 'VOD', 'DVD']):
        log(f"  SKIP (non-music): {data['album']}")
        return None

    if not data['crawl_status']:
        data['crawl_status'] = 'success'

    log(f"  ADDED: {data.get('album','?')} / {data.get('artist','?')}")
    return data

def scrape_with_browser():
    log("Starting browser scrape for ProgressoR")
    with sync_playwright() as p:
        # Try http:// (https:// fails due to SSL cipher mismatch on server)
        browser_url = "http://www.progressor.net"
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            log(f"Browser launch error: {e}")
            return

        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Main listing pages to try
        listing_urls = [
            "http://www.progressor.net/review/detailed.html",
            "http://www.progressor.net/review/short.html",
        ]

        all_article_urls = set()

        for list_url in listing_urls:
            urls = scrape_listing(page, list_url)
            all_article_urls.update(urls)

        log(f"Total unique article URLs: {len(all_article_urls)}")

        for article_url in all_article_urls:
            data = scrape_review_detail(page, article_url)
            if data:
                RESULTS.append(data)

        browser.close()

if __name__ == "__main__":
    log(f"Cutoff date: {CUTOFF_DATE.date()}")
    scrape_with_browser()
    log(f"Total items: {len(RESULTS)}")
    with open(OUTPUT, "w") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)
    log(f"Written to {OUTPUT}")