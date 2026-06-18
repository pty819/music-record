#!/usr/bin/env python3
"""
scrape_boomkat.py — Camoufox-based scraper for Boomkat editorial reviews.

Boomkat is an independent music store at https://boomkat.com with detailed
editorial descriptions for each product. Cloudflare blocks RSS, so we use
Camoufox (Firefox-based) browser.

Strategy:
  1. Navigate to New Releases listing (100 items/page, pages 1-2)
  2. Extract products by their HTML structure (date headers, div.listing2__product)
  3. Parse: artist, album, label, genre, description, URL
  4. Visit each product page for full body text
  5. Filter by 36h cutoff
  6. Output structured JSON

Usage:
  python3 scrape_boomkat.py [--pages 1] [--days 1.5] [--limit 50]
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
NEW_RELEASES_URL = "https://boomkat.com/new-releases"

SITE_ID = "boomkat"
SOURCE = "Boomkat"
TAGS_DEFAULT = "experimental,electronic,noise,ambient,modern composition"
USER_ID = "scraper_boomkat"
SESSION_KEY = "session_bk"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

NON_MUSIC_RE = re.compile(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', re.IGNORECASE)


def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Make a JSON API call to the Camoufox REST server."""
    url = f"{CAMOFOX_BASE}{path}"
    # Inject auth into every request body
    if body is None:
        body = {}
    if "userId" not in body and "sessionKey" not in body:
        body = {**body, "userId": USER_ID, "sessionKey": SESSION_KEY}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CAMOFOX_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {body_text}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


def parse_date(date_str: str) -> str | None:
    """Parse Boomkat date formats like 'Today', '29 May 2026' into ISO date."""
    date_str = date_str.strip()
    today = datetime.now(timezone.utc).date()

    if date_str.lower() == "today":
        return today.isoformat()
    if date_str.lower() == "yesterday":
        return (today - timedelta(days=1)).isoformat()

    parts = date_str.replace(",", "").split()
    if len(parts) >= 3:
        day_str = parts[0]
        month_name = parts[1].lower()
        year_str = parts[2]
        month = MONTHS.get(month_name)
        if month and day_str.isdigit() and year_str.isdigit():
            try:
                return datetime(int(year_str), month, int(day_str)).date().isoformat()
            except ValueError:
                pass
    return None


# JS to extract ALL products from the current listing page
# Structure: date-header div followed by listing2__product divs
EXTRACT_PRODUCTS_JS = """
() => {
    const results = [];
    const productBlocks = document.querySelectorAll('.listing2__product');

    // Get all date headers and their positions
    const dateHeaders = document.querySelectorAll('.date-header');
    const dateRanges = [];
    for (const dh of dateHeaders) {
        // Find the product index range for this date
        let startIdx = -1;
        let endIdx = -1;
        for (let i = 0; i < productBlocks.length; i++) {
            const pos = productBlocks[i].compareDocumentPosition(dh);
            // Check if dh comes before this product
            if (dh.compareDocumentPosition(productBlocks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
                if (startIdx === -1) startIdx = i;
            }
        }
        // End of this section is either the next date header or end of products
        const nextDH = dh.nextElementSibling && dh.nextElementSibling.classList.contains('date-header')
            ? dh.nextElementSibling : null;
        if (nextDH) {
            for (let i = 0; i < productBlocks.length; i++) {
                if (nextDH.compareDocumentPosition(productBlocks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
                    endIdx = i;
                    break;
                }
            }
        }
        if (endIdx === -1) endIdx = productBlocks.length;
        dateRanges.push({
            date: dh.textContent.trim(),
            start: startIdx === -1 ? 0 : startIdx,
            end: endIdx === -1 ? productBlocks.length : endIdx
        });
    }

    // Process each product block
    for (let i = 0; i < productBlocks.length; i++) {
        const block = productBlocks[i];

        // Determine the date for this product
        let dateText = '';
        for (const dr of dateRanges) {
            if (i >= dr.start && i < dr.end) {
                dateText = dr.date;
                break;
            }
        }

        // Find the link that has <strong> and .album-title (not the image link)
        const allLinks = block.querySelectorAll('a[href*="/products/"]');
        let link = null;
        for (const al of allLinks) {
            if (al.querySelector('strong') && al.querySelector('.album-title')) {
                link = al;
                break;
            }
        }
        if (!link) {
            // Fallback: just use the first link with strong
            for (const al of allLinks) {
                if (al.querySelector('strong')) {
                    link = al;
                    break;
                }
            }
        }
        if (!link) continue;
        const url = link.href;

        // Artist is in <strong> inside the link
        const strong = link.querySelector('strong');
        const artist = strong ? strong.textContent.trim() : '';

        // Album is in span.album-title
        const albumSpan = link.querySelector('.album-title');
        const album = albumSpan ? albumSpan.textContent.trim() : '';

        // Catalog number
        const catnumEl = block.querySelector('.catnum');
        const catnum = catnumEl ? catnumEl.textContent.trim() : '';

        // Label
        const labelEl = block.querySelector('.details a[href*="/labels/"]');
        const label = labelEl ? labelEl.textContent.trim() : '';

        // Genre
        const genreEl = block.querySelector('.genre');
        let genre = genreEl ? genreEl.textContent.trim() : '';
        // Clean up HTML entities and whitespace
        genre = genre.replace(/&nbsp;/g, ' ').replace(/\\s+/g, ' ').trim();
        // Remove leading pipe/separator artifacts
        genre = genre.replace(/^\\s*\\|[\\s\\|]*/g, '').trim();

        // Description text
        const descEl = block.querySelector('.description .text');
        let description = descEl ? descEl.textContent.trim() : '';
        // Clean up whitespace
        description = description.replace(/\\s+/g, ' ').trim();

        results.push({
            url: url,
            artist: artist,
            album: album,
            label: label,
            genre: genre,
            description: description,
            date_text: dateText,
            catnum: catnum,
        });
    }

    return results;
}
"""

# JS to extract full product page info
GET_PRODUCT_BODY_JS = """
() => {
    // Find the "Boomkat Product Review:" section
    const bodyText = document.body.innerText;
    const reviewMarker = 'Boomkat Product Review:';
    const tracksMarker = 'Tracks for';
    
    // Try to find the review text
    let body = '';
    const reviewIdx = bodyText.indexOf(reviewMarker);
    if (reviewIdx >= 0) {
        const startIdx = reviewIdx + reviewMarker.length;
        // Find where the review ends - look for tracklist or next section
        let endIdx = bodyText.indexOf(tracksMarker, startIdx);
        if (endIdx < 0 || endIdx - startIdx > 8000) {
            // Try other markers
            for (const marker of ['Tracks', 'Tracklist', 'Format', 'Related Products', 'You might also like']) {
                const idx = bodyText.indexOf(marker, startIdx);
                if (idx > 0 && idx - startIdx < 8000) {
                    endIdx = idx;
                    break;
                }
            }
        }
        if (endIdx < 0 || endIdx > bodyText.length) {
            endIdx = startIdx + 5000;
        }
        body = bodyText.substring(startIdx, endIdx).trim();
    }
    
    // Fallback: try to get the content
    if (!body) {
        const contentEl = document.querySelector('.content') || document.body;
        body = contentEl.textContent.trim();
    }

    // Get title from h1
    const h1 = document.querySelector('h1');
    const title = h1 ? h1.textContent.trim() : '';

    return {
        body: body.substring(0, 10000),
        title: title,
    };
}
"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape Boomkat editorial reviews")
    parser.add_argument("--limit", type=int, default=100, help="Max products to process per page")
    parser.add_argument("--pages", type=int, default=2, help="Number of listing pages (max 2)")
    parser.add_argument("--days", type=float, default=1.5, help="Max age in days")
    parser.add_argument("--date", type=str, default=None, help="Explicit cutoff date YYYY-MM-DD")
    parser.add_argument("--no-product-pages", action="store_true", help="Skip visiting individual product pages")
    args = parser.parse_args()
    pages = min(args.pages, 2)
    limit = min(args.limit, 100)

    today = datetime.now(timezone.utc).date()
    if args.date:
        try:
            cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.stderr.write(f"ERROR: Invalid --date. Use YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        cutoff_date = today - timedelta(days=args.days)

    sys.stderr.write(
        f"Boomkat scraper — Today: {today}, Cutoff: {cutoff_date}, Pages: {pages}, Limit: {limit}\n"
    )

    # Step 1: Create tab and go to New Releases
    sys.stderr.write(f"Creating tab and navigating to New Releases...\n")
    tab_resp = _api("POST", "/tabs", {
        "userId": USER_ID,
        "sessionKey": SESSION_KEY,
        "url": f"{NEW_RELEASES_URL}?show=100",
    })
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        result = {"meta": {"total": 0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    all_items = []
    try:
        time.sleep(2)

        # Step 2: Extract products from each page
        all_products_raw = []
        seen_urls = set()

        for page_num in range(1, pages + 1):
            sys.stderr.write(f"\n=== Page {page_num} ===\n")

            if page_num > 1:
                _api("POST", f"/tabs/{tab_id}/navigate", {
                    "url": f"{NEW_RELEASES_URL}?show=100&page={page_num}",
                })
                time.sleep(2)

            resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                "expression": EXTRACT_PRODUCTS_JS,
            })
            products = resp.get("result") or []
            sys.stderr.write(f"Found {len(products)} products on page {page_num}\n")

            for p in products:
                url = p.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_products_raw.append(p)

        sys.stderr.write(f"\nTotal unique products: {len(all_products_raw)}\n")

        # Step 3: Process products with cutoff filter
        for p in all_products_raw[:limit]:
            url = p.get("url", "")
            artist = p.get("artist", "")
            album = p.get("album", "")
            description = p.get("description", "")
            label = p.get("label", "")
            genre = p.get("genre", "")
            date_text = p.get("date_text", "")

            # Parse date
            pub_date = parse_date(date_text) if date_text else today.isoformat()
            if not pub_date:
                pub_date = today.isoformat()

            # Check cutoff
            try:
                item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                if item_date < cutoff_date:
                    continue
            except ValueError:
                pass

            # Non-music filter
            combined = f"{artist} {album} {genre} {label}"
            if NON_MUSIC_RE.search(combined):
                sys.stderr.write(f"  SKIP (non-music): {artist} - {album}\n")
                continue

            # Clean description for excerpt
            excerpt = ""
            if description:
                excerpt = unescape(description)[:500]

            item = {
                "album": album,
                "artist": artist,
                "score": None,
                "url": url,
                "source": SOURCE,
                "pub_date": pub_date,
                "tags": genre if genre else TAGS_DEFAULT,
                "excerpt": excerpt,
                "body": description,
                "site_id": SITE_ID,
                "crawl_status": "success",
                "type": "feature",
            }
            all_items.append(item)
            sys.stderr.write(f"  OK — {artist or '?'} : {album} ({pub_date})\n")

        # Step 4: Visit individual product pages for full body text
        if not args.no_product_pages and all_items:
            sys.stderr.write(f"\n=== Visiting {len(all_items)} product pages for full body ===\n")
            # Create a dedicated tab for product pages to avoid page scroll issues
            for i, item in enumerate(all_items):
                url = item["url"]
                sys.stderr.write(f"  [{i+1}/{len(all_items)}] {item['artist'] or '?'} : {item['album'][:40]}...\n")

                try:
                    _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                    time.sleep(1.5)

                    resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                        "expression": GET_PRODUCT_BODY_JS,
                    })
                    detail = resp.get("result") or {}
                    body = (detail.get("body") or "").strip()

                    if body:
                        item["body"] = body
                        if not item["excerpt"]:
                            item["excerpt"] = body[:500]

                    sys.stderr.write(f"    body: {len(body)} chars\n")

                except Exception as e:
                    sys.stderr.write(f"    ERROR: {e}\n")
                    item["crawl_status"] = "partial"

        # Step 5: Output
        result = {
            "meta": {
                "total": len(all_items),
                "scraped_at": today.isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
            },
            "items": all_items,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.stderr.write(f"\nTotal: {len(all_items)} items\n")

    finally:
        try:
            _api("DELETE", f"/tabs/{tab_id}")
            sys.stderr.write(f"Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"WARNING: Failed to close tab: {e}\n")


if __name__ == "__main__":
    main()
