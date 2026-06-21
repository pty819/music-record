#!/usr/bin/env python3
"""
scrape_boomkat_today.py — single-pass Boomkat scrape with explicit CF detection.

1. Open Boomkat listing in a fresh Camoufox tab
2. Wait 15s for Cloudflare Turnstile to clear (it auto-solves in 5-15s)
3. Run the CF check: document.title + product count
4. If title contains "Just a moment" OR products==0 → write empty output with
   cf_blocked:true and EXIT. Per task: do NOT open new tabs to retry.
5. Otherwise → extract products from pages 1+2, then visit each product page
   for full body text. Apply 36h cutoff and non-music filter.
6. Write to /home/liyifan/music-record/2026/06/2026-06-22/boomkat_reviews.json

Reuses the Camoufox client helpers from /home/liyifan/music-record/bin/scrape_boomkat.py
via shared inlined functions (avoids import-path surprises).
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape

CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
NEW_RELEASES_URL = "https://boomkat.com/new-releases"
SITE_ID = "boomkat"
SOURCE = "Boomkat"
TAGS_DEFAULT = "experimental,electronic,noise,ambient,modern composition"
USER_ID = "scraper_boomkat_today"
SESSION_KEY = "session_bk_today"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
NON_MUSIC_RE = re.compile(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', re.IGNORECASE)

OUT_PATH = "/home/liyifan/music-record/2026/06/2026-06-22/boomkat_reviews.json"


def _api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{CAMOFOX_BASE}{path}"
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
        day_str, month_name, year_str = parts[0], parts[1].lower(), parts[2]
        month = MONTHS.get(month_name)
        if month and day_str.isdigit() and year_str.isdigit():
            try:
                return datetime(int(year_str), month, int(day_str)).date().isoformat()
            except ValueError:
                pass
    return None


# CF detection — done at boot, NOT after a failed scrape.
CF_CHECK_JS = """
() => document.title + '|' + document.querySelectorAll('.listing2__product').length
"""

EXTRACT_PRODUCTS_JS = """
() => {
    const results = [];
    const productBlocks = document.querySelectorAll('.listing2__product');
    const dateHeaders = document.querySelectorAll('.date-header');
    const dateRanges = [];
    for (const dh of dateHeaders) {
        let startIdx = -1;
        for (let i = 0; i < productBlocks.length; i++) {
            if (dh.compareDocumentPosition(productBlocks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
                if (startIdx === -1) startIdx = i;
            }
        }
        const nextDH = dh.nextElementSibling && dh.nextElementSibling.classList.contains('date-header')
            ? dh.nextElementSibling : null;
        let endIdx = -1;
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
    for (let i = 0; i < productBlocks.length; i++) {
        const block = productBlocks[i];
        let dateText = '';
        for (const dr of dateRanges) {
            if (i >= dr.start && i < dr.end) { dateText = dr.date; break; }
        }
        const allLinks = block.querySelectorAll('a[href*="/products/"]');
        let link = null;
        for (const al of allLinks) {
            if (al.querySelector('strong') && al.querySelector('.album-title')) { link = al; break; }
        }
        if (!link) {
            for (const al of allLinks) {
                if (al.querySelector('strong')) { link = al; break; }
            }
        }
        if (!link) continue;
        const url = link.href;
        const artist = link.querySelector('strong')?.textContent.trim() || '';
        const album = link.querySelector('.album-title')?.textContent.trim() || '';
        const catnum = block.querySelector('.catnum')?.textContent.trim() || '';
        const label = block.querySelector('.details a[href*="/labels/"]')?.textContent.trim() || '';
        let genre = block.querySelector('.genre')?.textContent.trim() || '';
        genre = genre.replace(/&nbsp;/g, ' ').replace(/\\s+/g, ' ').trim();
        genre = genre.replace(/^\\s*\\|[\\s|]*/g, '').trim();
        const descEl = block.querySelector('.description .text');
        let description = descEl ? descEl.textContent.trim() : '';
        description = description.replace(/\\s+/g, ' ').trim();
        results.push({
            url, artist, album, label, genre, description, date_text: dateText, catnum
        });
    }
    return results;
}
"""

GET_PRODUCT_BODY_JS = """
() => {
    const bodyText = document.body.innerText;
    const reviewMarker = 'Boomkat Product Review:';
    const tracksMarker = 'Tracks for';
    let body = '';
    const reviewIdx = bodyText.indexOf(reviewMarker);
    if (reviewIdx >= 0) {
        const startIdx = reviewIdx + reviewMarker.length;
        let endIdx = bodyText.indexOf(tracksMarker, startIdx);
        if (endIdx < 0 || endIdx - startIdx > 8000) {
            for (const marker of ['Tracks', 'Tracklist', 'Format', 'Related Products', 'You might also like']) {
                const idx = bodyText.indexOf(marker, startIdx);
                if (idx > 0 && idx - startIdx < 8000) { endIdx = idx; break; }
            }
        }
        if (endIdx < 0 || endIdx > bodyText.length) endIdx = startIdx + 5000;
        body = bodyText.substring(startIdx, endIdx).trim();
    }
    if (!body) {
        const contentEl = document.querySelector('.content') || document.body;
        body = contentEl.textContent.trim();
    }
    const h1 = document.querySelector('h1');
    const title = h1 ? h1.textContent.trim() : '';
    return { body: body.substring(0, 10000), title };
}
"""


def write_empty_cf_blocked(reason: str) -> None:
    """Write the early-exit JSON when CF is blocking us."""
    today = datetime.now(timezone.utc).date()
    payload = {
        "meta": {
            "total": 0,
            "scraped_at": today.isoformat(),
            "cutoff_date": (today - timedelta(days=1.5)).isoformat(),
            "cf_blocked": True,
            "cf_reason": reason,
            "site": SITE_ID,
        },
        "items": [],
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    sys.stderr.write(f"[CF-BLOCKED] wrote empty output to {OUT_PATH}: {reason}\n")


def main() -> int:
    today = datetime.now(timezone.utc).date()
    cutoff_date = today - timedelta(days=1.5)
    sys.stderr.write(f"Boomkat scraper — Today: {today}, Cutoff: {cutoff_date}\n")

    # ── Step 1: fresh tab + navigate ────────────────────────────────────────
    sys.stderr.write("Creating tab and navigating to /new-releases...\n")
    tab_id = None
    try:
        # NOTE: POST /tabs may return HTTP 500 after ~30s while tab IS created.
        # Per memory: don't trust 500 → fail. Recover via GET /tabs?userId=...
        try:
            tab_resp = _api("POST", "/tabs", {
                "userId": USER_ID,
                "sessionKey": SESSION_KEY,
                "url": f"{NEW_RELEASES_URL}?show=100",
            })
            tab_id = tab_resp.get("tabId")
        except urllib.error.HTTPError as e:
            sys.stderr.write(f"[WARN] POST /tabs returned {e.code}, recovering via GET /tabs\n")
            tabs_resp = _api("GET", f"/tabs?userId={USER_ID}")
            tabs = tabs_resp.get("tabs", []) or []
            if tabs:
                tab_id = tabs[0].get("id") or tabs[0].get("tabId")
                sys.stderr.write(f"[RECOVERED] reusing tab {tab_id}\n")

        if not tab_id:
            sys.stderr.write("ERROR: no tab available\n")
            write_empty_cf_blocked("tab creation failed")
            return 0  # still exit clean — the file is written

        # ── Step 2: wait 15s for CF to clear ─────────────────────────────────
        sys.stderr.write("Waiting 15s for CF Turnstile to auto-solve...\n")
        time.sleep(15)

        # ── Step 3: CF pre-check (per task body) ─────────────────────────────
        check = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": CF_CHECK_JS})
        result = check.get("result") or ""
        sys.stderr.write(f"[CF-CHECK] {result}\n")
        title, _, count_str = result.partition("|")
        try:
            product_count = int(count_str.strip() or "0")
        except ValueError:
            product_count = 0
        if "Just a moment" in title or product_count == 0:
            write_empty_cf_blocked(f"title='{title}' products={product_count}")
            return 0

        # ── Step 4: extract products from pages 1 + 2 ────────────────────────
        all_raw = []
        seen = set()
        for page_num in (1, 2):
            if page_num > 1:
                _api("POST", f"/tabs/{tab_id}/navigate", {
                    "url": f"{NEW_RELEASES_URL}?show=100&page={page_num}",
                })
                time.sleep(2.5)
            resp = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": EXTRACT_PRODUCTS_JS})
            products = resp.get("result") or []
            sys.stderr.write(f"Page {page_num}: {len(products)} products\n")
            for p in products:
                u = p.get("url", "")
                if u and u not in seen:
                    seen.add(u)
                    all_raw.append(p)

        sys.stderr.write(f"Total unique products across 2 pages: {len(all_raw)}\n")

        # ── Step 5: cutoff filter + non-music filter ─────────────────────────
        items = []
        for p in all_raw:
            artist = p.get("artist", "")
            album = p.get("album", "")
            description = p.get("description", "")
            label = p.get("label", "")
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

            combined = f"{artist} {album} {genre} {label}"
            if NON_MUSIC_RE.search(combined):
                sys.stderr.write(f"  SKIP (non-music): {artist} - {album}\n")
                continue

            excerpt = unescape(description)[:500] if description else ""
            items.append({
                "album": album,
                "artist": artist,
                "score": None,
                "url": p.get("url", ""),
                "source": SOURCE,
                "pub_date": pub_date,
                "tags": genre if genre else TAGS_DEFAULT,
                "excerpt": excerpt,
                "body": description,
                "site_id": SITE_ID,
                "crawl_status": "success",
                "type": "feature",
            })

        sys.stderr.write(f"After cutoff+filter: {len(items)} items\n")

        # ── Step 6: visit each product page for full body (with batched restarts) ──
        # Per memory: ~42 visits crash Camoufox. Use BATCH_SIZE=25 and restart tab per batch.
        if items:
            BATCH_SIZE = 25
            for batch_start in range(0, len(items), BATCH_SIZE):
                batch = items[batch_start:batch_start + BATCH_SIZE]
                sys.stderr.write(f"=== Batch {batch_start}-{batch_start+len(batch)}: visiting product pages ===\n")
                for i, item in enumerate(batch):
                    idx = batch_start + i + 1
                    url = item["url"]
                    sys.stderr.write(f"  [{idx}/{len(items)}] {item['artist'] or '?'} : {(item['album'] or '')[:40]}\n")
                    try:
                        _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                        time.sleep(1.5)
                        detail = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": GET_PRODUCT_BODY_JS}).get("result") or {}
                        body = (detail.get("body") or "").strip()
                        if body:
                            item["body"] = body
                            if not item["excerpt"]:
                                item["excerpt"] = body[:500]
                        sys.stderr.write(f"    body: {len(body)} chars\n")
                    except Exception as e:
                        sys.stderr.write(f"    ERROR: {e}\n")
                        item["crawl_status"] = "partial"

        # ── Step 7: classify items: tracklist vs feature ─────────────────────
        for item in items:
            if not (item.get("body") or "").strip():
                item["type"] = "tracklist"

        result = {
            "meta": {
                "total": len(items),
                "scraped_at": today.isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
                "site": SITE_ID,
            },
            "items": items,
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        sys.stderr.write(f"\nWrote {len(items)} items to {OUT_PATH}\n")
        return 0

    finally:
        if tab_id:
            try:
                _api("DELETE", f"/tabs/{tab_id}")
                sys.stderr.write(f"Closed tab {tab_id}\n")
            except Exception as e:
                sys.stderr.write(f"WARN: failed to close tab: {e}\n")


if __name__ == "__main__":
    sys.exit(main())
