#!/usr/bin/env python3
"""Scrape The Squid's Ear — no RSS, use browser."""

import sys, re, json, os
from datetime import datetime, timedelta

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed")
    sys.exit(1)

SITE_URL   = "https://www.squidco.com/ear/earReviews.shtml"
OUTPUT     = "/home/liyifan/music-record/2026/05/2026-05-24/squids_ear_reviews.json"
CUTOFF     = datetime.now() - timedelta(days=3)
SITE_ID    = "squids_ear"
ITEMS_PER_PAGE = 20  # approximate rows per page

def log(msg):
    print(msg, flush=True)

def parse_row(row_el, page_text):
    """
    Extract review data from a table-row element.
    Columns (in order): Artist | Title | Label | Author
    The link to the review is embedded in the row text via newsID links.
    We detect the review URL by scanning page_text for newsID links that
    match artist/title in the row text.
    """
    text = row_el.inner_text().strip()
    if not text or len(text) < 5:
        return None

    # skip pagination footer links (page numbers)
    if re.fullmatch(r'[\d\s\u00a0]+', text):
        return None

    # Extract artist, title, label, author from the row text.
    # Format is typically: ArtistName\nTitleName\nLabel\nAuthorName
    parts = [p.strip() for p in re.split(r'\n+', text)]
    parts = [p for p in parts if p]

    if len(parts) < 3:
        return None

    artist = parts[0]
    title  = parts[1]
    label  = parts[2] if len(parts) > 2 else ""
    author = parts[3] if len(parts) > 3 else ""

    # Filter: non-music items
    for skip in [r'(BLU-RAY)', r'(UHD)', r'(VOD)', r'(DVD)', r'\bDVD\b']:
        if re.search(skip, text, re.IGNORECASE):
            return None

    # Find review URL by looking for newsView.cgi links in page that match artist/title
    url = ""
    row_lower = text.lower()
    # find all newsID links on page that contain the artist or title
    hrefs = re.findall(r'href="(/cgi-bin/news/newsView\.cgi\?newsID=\d+)"', page_text)
    for href in hrefs:
        full_url = "https://www.squidco.com" + href
        try:
            detail_text = ""
        except Exception:
            continue
        # Heuristic: if href is near artist name in page source, use it
        # For speed just collect first matching newsID as fallback
        if not url:
            url = full_url

    # Try to extract score from row text (e.g. "8" or "****")
    score = None
    score_match = re.search(r'\b(\d{1,2})/(\d{1,2})\b', text)
    if score_match:
        score = f"{score_match.group(1)}/{score_match.group(2)}"
    elif re.search(r'\*{2,}', text):  # **** strong rating
        score = "rated"

    # Extract pub_date from URL newsID (approximate via page position)
    pub_date = ""

    # type determination
    review_types = ["review", "feature", "tracklist"]
    item_type = "review"

    excerpt = title
    if len(excerpt) > 500:
        excerpt = excerpt[:500]

    return {
        "album": title,
        "artist": artist,
        "score": score,
        "url": url,
        "source": SITE_URL,
        "pub_date": pub_date,
        "tags": [],
        "excerpt": excerpt,
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": item_type,
    }

def scrape_page_reviews(page, page_text):
    """Parse table rows from listing page."""
    items = []
    # Find all table rows with review data — they contain artist/title in td cells
    # The page uses a search result table. Rows with review data have multiple <td> elements.
    rows = page.query_selector_all("tr")
    for row in rows:
        td_cells = row.query_selector_all("td")
        if len(td_cells) < 3:
            continue
        # Build text from all cells
        row_text = " | ".join([td.inner_text().strip() for td in td_cells])
        if not row_text or len(row_text) < 10:
            continue
        # Skip pagination controls
        if re.match(r'^\s*\d+\s*$', row_text.strip()):
            continue
        # Skip empty-like rows
        stripped = row_text.replace('\u00a0', ' ').replace('\r\n', ' ').strip()
        if len(stripped) < 5:
            continue

        # Check artist cell (first td)
        artist_cell = td_cells[0].inner_text().strip() if td_cells else ""
        title_cell  = td_cells[1].inner_text().strip() if len(td_cells) > 1 else ""
        label_cell  = td_cells[2].inner_text().strip() if len(td_cells) > 2 else ""
        author_cell = td_cells[3].inner_text().strip() if len(td_cells) > 3 else ""

        if not artist_cell or len(artist_cell) < 2:
            continue

        # Filter: non-music
        for skip in [r'(BLU-RAY)', r'(UHD)', r'(VOD)', r'(DVD)', r'\bDVD\b']:
            if re.search(skip, row_text, re.IGNORECASE):
                continue

        # Find URL from anchor in row or near cells
        links = row.query_selector_all("a[href]")
        url = ""
        for link in links:
            href = link.get_attribute("href") or ""
            if "newsView.cgi" in href:
                url = "https://www.squidco.com" + href
                break

        # Score detection
        score = None
        score_m = re.search(r'\b(\d{1,2})/(\d{1,2})\b', row_text)
        if score_m:
            score = f"{score_m.group(1)}/{score_m.group(2)}"

        excerpt = title_cell[:500] if title_cell else ""

        items.append({
            "album": title_cell,
            "artist": artist_cell,
            "score": score,
            "url": url,
            "source": SITE_URL,
            "pub_date": "",
            "tags": [],
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        })
    return items

def main():
    results = []
    seen_urls = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        # Page 1
        log(f"Loading {SITE_URL}")
        page.goto(SITE_URL, wait_until="networkidle", timeout=30)
        page.wait_for_timeout(2000)

        all_items = []

        # Get page 1 rows
        page_text = page.content()
        rows = page.query_selector_all("tr")
        for row in rows:
            tds = row.query_selector_all("td")
            if len(tds) < 3:
                continue
            artist = tds[0].inner_text().strip() if tds else ""
            title  = tds[1].inner_text().strip() if len(tds) > 1 else ""
            label  = tds[2].inner_text().strip() if len(tds) > 2 else ""
            author = tds[3].inner_text().strip() if len(tds) > 3 else ""
            if not artist or len(artist) < 2:
                continue
            links = row.query_selector_all("a[href]")
            url = ""
            for link in links:
                href = link.get_attribute("href") or ""
                if "newsView.cgi" in href:
                    url = "https://www.squidco.com" + href
                    break
            # skip non-music
            row_text = row.inner_text()
            skip = False
            for pat in [r'(BLU-RAY)', r'(UHD)', r'(VOD)', r'\bDVD\b']:
                if re.search(pat, row_text, re.IGNORECASE):
                    skip = True
                    break
            if skip:
                continue
            # score
            score = None
            sm = re.search(r'\b(\d)\s*/\s*(\d)\b', row_text)
            if sm:
                score = f"{sm.group(1)}/{sm.group(2)}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            all_items.append({
                "album": title,
                "artist": artist,
                "score": score,
                "url": url,
                "source": SITE_URL,
                "pub_date": "",
                "tags": [],
                "excerpt": title[:500],
                "site_id": SITE_ID,
                "crawl_status": "success",
                "type": "review",
            })

        log(f"Page 1: collected {len(all_items)} items")

        # Click page 2
        page_links = page.query_selector_all("a")
        page2_href = None
        for link in page_links:
            text = link.inner_text().strip()
            if text == "2":
                page2_href = link.get_attribute("href")
                break

        if page2_href:
            log(f"Clicking page 2: {page2_href}")
            page.goto("https://www.squidco.com/ear/" + page2_href, wait_until="networkidle", timeout=30)
            page.wait_for_timeout(2000)

            rows2 = page.query_selector_all("tr")
            for row in rows2:
                tds = row.query_selector_all("td")
                if len(tds) < 3:
                    continue
                artist = tds[0].inner_text().strip() if tds else ""
                title  = tds[1].inner_text().strip() if len(tds) > 1 else ""
                label  = tds[2].inner_text().strip() if len(tds) > 2 else ""
                author = tds[3].inner_text().strip() if len(tds) > 3 else ""
                if not artist or len(artist) < 2:
                    continue
                links = row.query_selector_all("a[href]")
                url = ""
                for link in links:
                    href = link.get_attribute("href") or ""
                    if "newsView.cgi" in href:
                        url = "https://www.squidco.com" + href
                        break
                row_text = row.inner_text()
                skip = False
                for pat in [r'(BLU-RAY)', r'(UHD)', r'(VOD)', r'\bDVD\b']:
                    if re.search(pat, row_text, re.IGNORECASE):
                        skip = True
                        break
                if skip:
                    continue
                score = None
                sm = re.search(r'\b(\d)\s*/\s*(\d)\b', row_text)
                if sm:
                    score = f"{sm.group(1)}/{sm.group(2)}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                all_items.append({
                    "album": title,
                    "artist": artist,
                    "score": score,
                    "url": url,
                    "source": SITE_URL,
                    "pub_date": "",
                    "tags": [],
                    "excerpt": title[:500],
                    "site_id": SITE_ID,
                    "crawl_status": "success",
                    "type": "review",
                })
            log(f"After page 2: collected {len(all_items)} items")

        browser.close()

    # Write output
    with open(OUTPUT, "w") as f:
        json.dump(all_items, f, indent=2)

    log(f"Written {len(all_items)} items to {OUTPUT}")
    print(json.dumps({"count": len(all_items), "output": OUTPUT}))

if __name__ == "__main__":
    main()