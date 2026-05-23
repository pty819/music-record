#!/usr/bin/env python3
"""Scrape The Squid's Ear via the browser-accessible listing.

Strategy: Use browser (headless Chromium via Playwright) to:
1. Load the reviews listing page
2. Extract artist/title/label/author + newsID URL from the table
3. For each row, check date via detail page fetch
4. Stop when all remaining items are older than 3 days
"""

import sys, re, json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed")
    sys.exit(1)

SITE_URL = "https://www.squidco.com/ear/earReviews.shtml"
OUTPUT  = "/home/liyifan/music-record/2026/05/2026-05-24/squids_ear_reviews.json"
CUTOFF  = datetime.now() - timedelta(days=3)
SITE_ID = "squids_ear"
BASE    = "https://www.squidco.com"

def log(msg):
    print(msg, flush=True)

def fetch_detail(url):
    """Fetch detail page, return date string or ''."""
    import subprocess
    res = subprocess.run(
        ['curl', '-sL', '--max-time', '15',
         '-H', 'User-Agent: Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
         url],
        capture_output=True, text=True, errors='replace')
    m = re.search(r'(\d{4}-\d{2}-\d{2})', res.stdout)
    return m.group(1) if m else ""

def main():
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        log(f"Loading {SITE_URL}")
        page.goto(SITE_URL, wait_until="domcontentloaded", timeout=30)
        page.wait_for_timeout(3000)

        # Wait for table to be populated
        try:
            page.wait_for_selector("table table table tr td a[href*='newsView.cgi']", timeout=10)
        except Exception:
            pass

        # Collect all rows from current page state
        rows = page.query_selector_all("table table table tr")
        log(f"Found {len(rows)} table rows in browser DOM")

        items = []
        for row in rows:
            tds = row.query_selector_all("td")
            if len(tds) < 4:
                continue
            # Get text of each cell
            cells = [td.inner_text().strip().replace('\u00a0', ' ') for td in tds]
            cells = [c for c in cells if c]
            if len(cells) < 3:
                continue

            # Get URL from first cell's anchor
            anchors = row.query_selector_all("td a[href*='newsView.cgi']")
            if not anchors:
                continue
            href = anchors[0].get_attribute("href")
            if not href:
                continue
            url = href if href.startswith('http') else BASE + href

            # Extract newsID
            m = re.search(r'newsID=(\d+)', url)
            news_id = m.group(1) if m else ""

            artist = cells[0]
            title  = cells[1] if len(cells) > 1 else ""
            label  = cells[2] if len(cells) > 2 else ""
            author = cells[3] if len(cells) > 3 else ""

            # Filter non-music
            text = artist + ' ' + title + ' ' + label
            if re.search(r'\b(BLU-RAY|UHD|VOD|DVD)\b', text, re.IGNORECASE):
                continue

            items.append(dict(news_id=news_id, artist=artist, title=title,
                           label=label, author=author, url=url))

        log(f"Parsed {len(items)} items from browser DOM")

        # Sort by news_id descending (newest first)
        items.sort(key=lambda x: int(x['news_id']) if x['news_id'].isdigit() else 0, reverse=True)
        log(f"newsID range: {items[0]['news_id']} – {items[-1]['news_id']}")

        # Batch process with parallel detail-page date fetches
        BATCH = 20
        i = 0
        batches = 0
        cutoff_found = False

        while i < len(items):
            batch = items[i:i+BATCH]
            with ThreadPoolExecutor(max_workers=BATCH) as ex:
                futures = {ex.submit(fetch_detail, r['url']): r for r in batch}
                for future in as_completed(futures):
                    r = futures[future]
                    r['pub_date'] = future.result()

            for r in batch:
                date_str = r.get('pub_date', '')
                if date_str:
                    try:
                        pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
                        if pub_dt < CUTOFF:
                            cutoff_found = True
                            continue
                    except ValueError:
                        pass

                results.append({
                    "album": r['title'],
                    "artist": r['artist'],
                    "score": None,
                    "url": r['url'],
                    "source": SITE_URL,
                    "pub_date": date_str,
                    "tags": [],
                    "excerpt": r['title'][:500],
                    "site_id": SITE_ID,
                    "crawl_status": "success",
                    "type": "review",
                })

            batches += 1
            log(f"Batch {batches}: scanned {min(i+BATCH, len(items))}/{len(items)}, collected {len(results)}")
            i += BATCH
            if cutoff_found:
                log("Cutoff reached")
                break

        browser.close()

    with open(OUTPUT, "w") as f:
        json.dump(results, f, indent=2)
    log(f"Written {len(results)} items to {OUTPUT}")
    print(json.dumps({"count": len(results), "output": OUTPUT}))

if __name__ == "__main__":
    main()