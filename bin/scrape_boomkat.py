#!/usr/bin/env python3
"""scrape_boomkat_pages.py — simplified Boomkat scraper using Camoufox."""
import json, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape

CAMOFOX_BASE = "http://127.0.0.1:9377"
API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
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
NON_MUSIC_RE = re.compile(r"\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)", re.IGNORECASE)

def api(method, path, body=None):
    url = f"{CAMOFOX_BASE}{path}"
    if body is None:
        body = {}
    if "userId" not in body:
        body = {**body, "userId": USER_ID, "sessionKey": SESSION_KEY}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        sys.stderr.write(f"[ERROR] HTTP {e.code} {method} {path}: {body_text}\n")
        raise

def parse_date(date_str):
    date_str = date_str.strip()
    today = datetime.now(timezone.utc).date()
    if date_str.lower() == "today":
        return today.isoformat()
    if date_str.lower() == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    parts = date_str.replace(",", "").split()
    if len(parts) >= 3:
        day_str, month_name, year_str = parts[0], parts[1].lower(), parts[2]
        month = MONTHS.get(month_name)
        if month and day_str.isdigit() and year_str.isdigit():
            try:
                return datetime(int(year_str), month, int(day_str)).date().isoformat()
            except ValueError:
                pass
    return None

# JS to extract products — single line, no multiline issues
EXTRACT_PRODUCTS_JS = """
(() => {
  const results = [];
  const blocks = document.querySelectorAll('.listing2__product');
  const dateHeaders = document.querySelectorAll('.date-header');
  const dateRanges = [];
  for (const dh of dateHeaders) {
    let startIdx = -1, endIdx = -1;
    for (let i = 0; i < blocks.length; i++) {
      if (dh.compareDocumentPosition(blocks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
        if (startIdx === -1) startIdx = i;
      }
    }
    const nextDH = dh.nextElementSibling && dh.nextElementSibling.classList.contains('date-header') ? dh.nextElementSibling : null;
    if (nextDH) {
      for (let i = 0; i < blocks.length; i++) {
        if (nextDH.compareDocumentPosition(blocks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) { endIdx = i; break; }
      }
    }
    if (endIdx === -1) endIdx = blocks.length;
    dateRanges.push({ date: dh.textContent.trim(), start: startIdx === -1 ? 0 : startIdx, end: endIdx });
  }
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    let dateText = '';
    for (const dr of dateRanges) { if (i >= dr.start && i < dr.end) { dateText = dr.date; break; } }
    const links = Array.from(b.querySelectorAll('a[href*=\"/products/\"]'));
    let link = null;
    for (const al of links) { if (al.querySelector('strong') && al.querySelector('.album-title')) { link = al; break; } }
    if (!link) { for (const al of links) { if (al.querySelector('strong')) { link = al; break; } } }
    if (!link) continue;
    const strong = link.querySelector('strong');
    const artist = strong ? strong.textContent.trim() : '';
    const albumSpan = link.querySelector('.album-title');
    const album = albumSpan ? albumSpan.textContent.trim() : '';
    const genreEl = b.querySelector('.genre');
    let genre = genreEl ? genreEl.textContent.trim() : '';
    genre = genre.replace(/&nbsp;/g, ' ').replace(/\\s+/g, ' ').trim();
    genre = genre.replace(/^\\s*\\|[\\s\\|]*/g, '').trim();
    const descEl = b.querySelector('.description .text');
    let desc = descEl ? descEl.textContent.trim() : '';
    desc = desc.replace(/\\s+/g, ' ').trim();
    results.push({ url: link.href, artist, album, genre, description: desc, date_text: dateText });
  }
  return JSON.stringify(results);
})()
"""

# Simplified single-line version for page body extraction
GET_PRODUCT_BODY_JS = """
(() => {
  const bodyText = document.body.innerText;
  const marker = 'Boomkat Product Review:';
  const tracksMarker = 'Tracks for';
  let body = '';
  const idx = bodyText.indexOf(marker);
  if (idx >= 0) {
    let endIdx = bodyText.indexOf(tracksMarker, idx + marker.length);
    if (endIdx < 0 || endIdx - idx > 8000) {
      for (const m of ['Tracks', 'Tracklist', 'Format', 'Related Products', 'You might also like']) {
        const mi = bodyText.indexOf(m, idx + marker.length);
        if (mi > 0 && mi - idx < 8000) { endIdx = mi; break; }
      }
    }
    if (endIdx < 0 || endIdx > bodyText.length) endIdx = idx + marker.length + 5000;
    body = bodyText.substring(idx + marker.length, endIdx).trim();
  }
  if (!body) {
    const ce = document.querySelector('.content') || document.body;
    body = ce.textContent.trim();
  }
  const h1 = document.querySelector('h1');
  return JSON.stringify({ body: body.substring(0, 10000), title: h1 ? h1.textContent.trim() : '' });
})()
"""

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--days", type=float, default=1.5)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--no-product-pages", action="store_true")
    args = parser.parse_args()
    pages = min(args.pages, 2)
    limit = min(args.limit, 100)

    today = datetime.now(timezone.utc).date()
    if args.date:
        try:
            cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.stderr.write("ERROR: Invalid --date.\n")
            sys.exit(1)
    else:
        cutoff_date = today - timedelta(days=args.days)

    sys.stderr.write(f"Boomkat scraper — Today: {today}, Cutoff: {cutoff_date}, Pages: {pages}, Limit: {limit}\n")

    # Step 1: Create tab to New Releases
    sys.stderr.write("Creating tab and navigating to New Releases...\n")
    tab_resp = api("POST", "/tabs", {"url": f"{NEW_RELEASES_URL}?show=100"})
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        result = {"meta": {"total": 0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    all_items = []
    try:
        time.sleep(3)  # Extra time for full render

        # Step 2: Extract products
        all_products_raw = []
        seen_urls = set()

        for page_num in range(1, pages + 1):
            sys.stderr.write(f"\n=== Page {page_num} ===\n")
            if page_num > 1:
                api("POST", f"/tabs/{tab_id}/navigate", {"url": f"{NEW_RELEASES_URL}?show=100&page={page_num}"})
                time.sleep(3)

            resp = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": EXTRACT_PRODUCTS_JS})
            raw_result = resp.get("result")
            if isinstance(raw_result, str):
                products = json.loads(raw_result)
            elif isinstance(raw_result, list):
                products = raw_result
            else:
                products = []
            sys.stderr.write(f"Found {len(products)} products on page {page_num}\n")

            for p in products:
                url = p.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_products_raw.append(p)

        sys.stderr.write(f"\nTotal unique products: {len(all_products_raw)}\n")

        # Step 3: Process with cutoff filter
        for p in all_products_raw[:limit]:
            url = p.get("url", "")
            artist = p.get("artist", "")
            album = p.get("album", "")
            description = p.get("description", "")
            genre = p.get("genre", "")
            date_text = p.get("date_text", "")

            pub_date = parse_date(date_text) if date_text else today.isoformat()
            if not pub_date:
                pub_date = today.isoformat()

            try:
                item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                if item_date < cutoff_date:
                    continue
            except ValueError:
                pass

            combined = f"{artist} {album} {genre}"
            if NON_MUSIC_RE.search(combined):
                sys.stderr.write(f"  SKIP (non-music): {artist} - {album}\n")
                continue

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

        # Step 4: Visit product pages for full body
        if not args.no_product_pages and all_items:
            sys.stderr.write(f"\n=== Visiting {len(all_items)} product pages for full body ===\n")
            for i, item in enumerate(all_items):
                url = item["url"]
                sys.stderr.write(f"  [{i+1}/{len(all_items)}] {item['artist'] or '?'} : {item['album'][:40]}...\n")
                try:
                    api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                    time.sleep(1.5)

                    resp = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": GET_PRODUCT_BODY_JS})
                    raw = resp.get("result")
                    if isinstance(raw, str):
                        detail = json.loads(raw)
                    else:
                        detail = raw or {}
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
            "meta": {"total": len(all_items), "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()},
            "items": all_items,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.stderr.write(f"\nTotal: {len(all_items)} items\n")

    finally:
        try:
            api("DELETE", f"/tabs/{tab_id}")
            sys.stderr.write(f"Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"WARNING: Failed to close tab: {e}\n")

if __name__ == "__main__":
    main()
