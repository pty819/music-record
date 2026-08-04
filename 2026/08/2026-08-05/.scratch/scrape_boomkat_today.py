#!/usr/bin/env python3
"""Scrape Boomkat — 2026-08-05 swarm."""

import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
NEW_RELEASES_URL = "https://boomkat.com/new-releases"

SITE_ID = "boomkat"
SOURCE = "Boomkat"
TAGS_DEFAULT = "experimental,electronic,noise,ambient,modern composition"
USER_ID = "swarm_2026_08_05"
SESSION_KEY = "boomkat"
OUT_PATH = "/home/liyifan/music-record/2026/08/2026-08-05/boomkat_reviews.json"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

NON_MUSIC_RE = re.compile(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', re.IGNORECASE)


def _api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{CAMOFOX_BASE}{path}"
    if body is None:
        body = {}
    if "userId" not in body:
        body["userId"] = USER_ID
    if "sessionKey" not in body:
        body["sessionKey"] = SESSION_KEY
    last_err = None
    for attempt in range(5):
        try:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, method=method,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {CAMOFOX_API_KEY}",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = e.read().decode()[:500]
            last_err = e
            if e.code in (500, 502, 503, 504) or "expired" in body_text.lower():
                sys.stderr.write(f"[RETRY {attempt+1}/5] HTTP {e.code}: {body_text[:120]}\n")
                time.sleep(2 + attempt * 2)
                continue
            sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {body_text}\n")
            raise
        except Exception as e:
            last_err = e
            sys.stderr.write(f"[RETRY {attempt+1}/5] {method} {path}: {e}\n")
            time.sleep(2 + attempt * 2)
    raise last_err


def parse_date(date_str: str) -> str | None:
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


EXTRACT_PRODUCTS_JS = r"""
() => {
    const results = [];
    const productBlocks = document.querySelectorAll('.listing2__product');
    const dateHeaders = document.querySelectorAll('.date-header');
    const dateRanges = [];
    for (const dh of dateHeaders) {
        let startIdx = -1, endIdx = -1;
        for (let i = 0; i < productBlocks.length; i++) {
            if (dh.compareDocumentPosition(productBlocks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
                if (startIdx === -1) startIdx = i;
            }
        }
        const nextDH = dh.nextElementSibling && dh.nextElementSibling.classList.contains('date-header')
            ? dh.nextElementSibling : null;
        if (nextDH) {
            for (let i = 0; i < productBlocks.length; i++) {
                if (nextDH.compareDocumentPosition(productBlocks[i]) & Node.DOCUMENT_POSITION_FOLLOWING) {
                    endIdx = i; break;
                }
            }
        }
        if (endIdx === -1) endIdx = productBlocks.length;
        dateRanges.push({
            date: dh.textContent.trim(),
            start: startIdx === -1 ? 0 : startIdx,
            end: endIdx === -1 ? productBlocks.length : endIdx,
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
        const strong = link.querySelector('strong');
        const artist = strong ? strong.textContent.trim() : '';
        const albumSpan = link.querySelector('.album-title');
        const album = albumSpan ? albumSpan.textContent.trim() : '';
        const catnumEl = block.querySelector('.catnum');
        const catnum = catnumEl ? catnumEl.textContent.trim() : '';
        const labelEl = block.querySelector('.details a[href*="/labels/"]');
        const label = labelEl ? labelEl.textContent.trim() : '';
        const genreEl = block.querySelector('.genre');
        let genre = genreEl ? genreEl.textContent.trim() : '';
        genre = genre.replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
        genre = genre.replace(/^\s*\|[\s\|]*/g, '').trim();
        const descEl = block.querySelector('.description .text');
        let description = descEl ? descEl.textContent.trim() : '';
        description = description.replace(/\s+/g, ' ').trim();
        results.push({
            url, artist, album, label, genre, description, date_text: dateText, catnum,
        });
    }
    return results;
}
"""


GET_PRODUCT_BODY_JS = r"""
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
            for (const m of ['Tracks', 'Tracklist', 'Related Products', 'You might also like']) {
                const idx = bodyText.indexOf(m, startIdx);
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
    return { body: body.substring(0, 10000), title: h1 ? h1.textContent.trim() : '' };
}
"""


CF_CHECK_JS = r"""
() => {
    const t = document.title || '';
    const n = document.querySelectorAll('.listing2__product').length;
    const bodyLen = (document.body.innerText || '').length;
    const hasCF = !!document.querySelector('#__cf_chl_rt_tk, [name*=cf-chl], .cf-browser-verification');
    return { title: t, products: n, bodyLen, hasCF, url: location.href };
}
"""


def wait_for_page(tab_id: str, want_products: int, max_wait: int = 30) -> bool:
    for i in range(max_wait):
        time.sleep(1)
        r = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": CF_CHECK_JS})
        info = r.get("result") or {}
        title = info.get("title", "")
        n = info.get("products", 0)
        bodyLen = info.get("bodyLen", 0)
        hasCF = info.get("hasCF", False)
        if hasCF or "Just a moment" in title or "Cloudflare" in title:
            sys.stderr.write(f"  [{i+1}s] CF challenge (title={title!r})\n")
            continue
        if not title and bodyLen < 500:
            sys.stderr.write(f"  [{i+1}s] page empty (title={title!r}, body={bodyLen})\n")
            continue
        if n >= want_products:
            sys.stderr.write(f"  [{i+1}s] page ready: {n} products\n")
            return True
        sys.stderr.write(f"  [{i+1}s] {n} products (title={title!r}, body={bodyLen})\n")
    return False


def main():
    today = datetime.now(timezone.utc).date()
    cutoff_date = today - timedelta(days=1.5)

    sys.stderr.write(f"Today: {today}, Cutoff: {cutoff_date}\n")

    tab_resp = _api("POST", "/tabs", {"url": f"{NEW_RELEASES_URL}?show=100"})
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        return
    sys.stderr.write(f"Created tab {tab_id}\n")
    time.sleep(5)

    all_items = []
    try:
        sys.stderr.write("Waiting for CF clearance + first page...\n")
        if not wait_for_page(tab_id, want_products=10, max_wait=45):
            r = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": CF_CHECK_JS})
            info = r.get("result") or {}
            title = info.get("title") or ""
            products = info.get("products", 0)
            bodyLen = info.get("bodyLen", 0)
            hasCF = info.get("hasCF", False)
            cf_blocked = hasCF or "Just a moment" in title or "Cloudflare" in title or (not title and bodyLen < 500)
            if cf_blocked:
                result = {
                    "meta": {
                        "total": 0,
                        "scraped_at": today.isoformat(),
                        "cutoff_date": cutoff_date.isoformat(),
                        "cf_blocked": True,
                        "site": "boomkat",
                    },
                    "items": [],
                }
                with open(OUT_PATH, "w") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                sys.stderr.write(f"CF BLOCKED (title={title!r}, products={products}, body={bodyLen}) — wrote empty result\n")
                print(json.dumps(result))
                return
            else:
                sys.stderr.write(f"WARNING: page slow, title={title!r}, products={products}, body={bodyLen}, continuing anyway\n")

        # Step 1: collect products from page 1 and 2
        all_products_raw = []
        seen_urls = set()
        for page_num in (1, 2):
            sys.stderr.write(f"\n=== Page {page_num} ===\n")
            if page_num > 1:
                _api("POST", f"/tabs/{tab_id}/navigate", {"url": f"{NEW_RELEASES_URL}?show=100&page={page_num}"})
                if not wait_for_page(tab_id, want_products=10, max_wait=20):
                    sys.stderr.write(f"  Page {page_num} didn't load — skipping\n")
                    continue
            resp = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": EXTRACT_PRODUCTS_JS})
            products = resp.get("result") or []
            sys.stderr.write(f"  Found {len(products)} products\n")
            for p in products:
                url = p.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_products_raw.append(p)

        sys.stderr.write(f"\nTotal unique products: {len(all_products_raw)}\n")

        # Step 2: cutoff filter
        candidates = []
        for p in all_products_raw:
            date_text = p.get("date_text", "")
            pub_date = parse_date(date_text) if date_text else None
            if not pub_date:
                pub_date = today.isoformat()
            try:
                item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                if item_date < cutoff_date:
                    continue
            except ValueError:
                continue

            combined = f"{p.get('artist','')} {p.get('album','')} {p.get('genre','')} {p.get('label','')}"
            if NON_MUSIC_RE.search(combined):
                continue

            candidates.append({**p, "pub_date": pub_date})

        sys.stderr.write(f"Within {cutoff_date} cutoff: {len(candidates)}\n")

        # Step 3: visit each product page for full body
        for i, p in enumerate(candidates):
            url = p["url"]
            artist = p.get("artist", "") or "?"
            album = (p.get("album") or "?")[:40]
            sys.stderr.write(f"  [{i+1}/{len(candidates)}] {artist} : {album}...\n")
            try:
                _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                time.sleep(1.5)
                resp = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": GET_PRODUCT_BODY_JS})
                detail = resp.get("result") or {}
                body = (detail.get("body") or "").strip()
                excerpt = (p.get("description") or "")[:500]
                if body and not excerpt:
                    excerpt = body[:500]
                item = {
                    "album": p.get("album", ""),
                    "artist": p.get("artist", ""),
                    "score": None,
                    "url": url,
                    "source": SOURCE,
                    "pub_date": p["pub_date"],
                    "tags": p.get("genre") or TAGS_DEFAULT,
                    "excerpt": excerpt,
                    "body": body or (p.get("description") or ""),
                    "site_id": SITE_ID,
                    "crawl_status": "success" if body else "partial",
                    "type": "feature",
                }
                all_items.append(item)
                sys.stderr.write(f"    body: {len(item['body'])} chars\n")
            except Exception as e:
                sys.stderr.write(f"    ERROR: {e}\n")
                item = {
                    "album": p.get("album", ""),
                    "artist": p.get("artist", ""),
                    "score": None,
                    "url": url,
                    "source": SOURCE,
                    "pub_date": p["pub_date"],
                    "tags": p.get("genre") or TAGS_DEFAULT,
                    "excerpt": (p.get("description") or "")[:500],
                    "body": p.get("description") or "",
                    "site_id": SITE_ID,
                    "crawl_status": "partial",
                    "type": "feature",
                }
                all_items.append(item)

        # Step 4: write output
        result = {
            "meta": {
                "total": len(all_items),
                "scraped_at": today.isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
                "site": "boomkat",
            },
            "items": all_items,
        }
        with open(OUT_PATH, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"\nWrote {len(all_items)} items to boomkat_reviews.json\n")
        print(json.dumps({"ok": True, "count": len(all_items)}))
    finally:
        try:
            _api("DELETE", f"/tabs/{tab_id}")
        except Exception:
            pass


if __name__ == "__main__":
    main()