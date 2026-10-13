#!/usr/bin/env python3
"""
scrape_all_about_jazz.py — Camoufox-based scraper for All About Jazz reviews.

All About Jazz (allaboutjazz.com/reviews) is a Cloudflare-fronted jazz review
aggregator. curl gets 403; we use the local Camoufox REST API on :9377.

Strategy:
  1. Create a tab, navigate to /reviews/ (page 1)
  2. Extract cards from div.row.data-row — album, artist, score (fa-star count),
     date, URL.
  3. Paginate to /reviews/&pg=2 (max 2 pages per spec)
  4. Filter by 36h cutoff (article date >= now-36h)
  5. Visit each article URL, extract body from div.main-inner
  6. Output standardized JSON

Usage:
  python3 scrape_all_about_jazz.py [--pages 2] [--days 1.5]
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
BASE_URL = "https://www.allaboutjazz.com"
LIST_URL = f"{BASE_URL}/reviews/"

SITE_ID = "all_about_jazz"
SOURCE = "All About Jazz"
TAGS_DEFAULT = "jazz"
USER_ID = "scraper_aaj"
SESSION_KEY = "session_aaj"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

NON_MUSIC_RE = re.compile(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', re.IGNORECASE)


def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Make a JSON API call to the Camoufox REST server."""
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
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


def parse_listing_date(text: str) -> str | None:
    """Parse 'June 4, 2026' or 'June 4 2026' into ISO date."""
    text = (text or "").strip()
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if not m:
        return None
    month_name, day_str, year_str = m.group(1), m.group(2), m.group(3)
    month = MONTHS.get(month_name.lower())
    if not month:
        return None
    try:
        return datetime(int(year_str), month, int(day_str)).date().isoformat()
    except ValueError:
        return None


# JS to extract all review cards from a /reviews/ listing page
EXTRACT_CARDS_JS = """
() => {
    const cards = document.querySelectorAll('div.row.data-row');
    const results = [];
    for (const card of cards) {
        // Album title + URL: h4 > a
        const h4 = card.querySelector('h4');
        if (!h4) continue;
        const link = h4.querySelector('a');
        if (!link) continue;
        const album = (h4.textContent || '').trim();
        const href = link.getAttribute('href') || '';

        // Artist: text node directly after h4 (within data-row-content)
        let artist = '';
        let sib = h4.nextSibling;
        while (sib) {
            if (sib.nodeType === Node.TEXT_NODE) {
                const t = (sib.textContent || '').trim();
                if (t) { artist = t; break; }
            }
            sib = sib.nextSibling;
        }

        // Star rating: count fa-star (filled) and fa-star-half-o (half)
        const filled = card.querySelectorAll('.fa.fa-star').length;
        const half = card.querySelectorAll('.fa.fa-star-half-o, .fa.fa-star-half').length;
        let score = null;
        if (filled || half) {
            score = filled + (half * 0.5);
        }

        // Date: in the SECOND .small (a <span class="small"> with byline+date)
        // The first .small is a <div> with the star icons
        const contentEl = card.querySelector('.data-row-content');
        const smallSpans = contentEl ? contentEl.querySelectorAll('span.small') : [];
        let dateText = '';
        if (smallSpans.length > 0) {
            const text = (smallSpans[0].innerText || '').trim();
            const m = text.match(/([A-Za-z]+\\s+\\d{1,2},?\\s+\\d{4})/);
            if (m) dateText = m[1];
        }

        results.push({
            album: album,
            artist: artist,
            url: href,
            score: score,
            date_text: dateText,
        });
    }
    return results;
}
"""


# JS to extract body text from a single article page
EXTRACT_BODY_JS = """
() => {
    // AAJ article body lives in div.main-inner
    const bodyEl = document.querySelector('div.main-inner') || document.querySelector('div.main-outer') || document.querySelector('article');
    let body = '';
    if (bodyEl) {
        // The review text is in a .bottom-20 div, but the FIRST .bottom-20 is the
        // "LIKE 2" button row. Pick the longest .bottom-20 div, which is the review.
        const bottomDivs = bodyEl.querySelectorAll('.bottom-20');
        let bestLen = 0;
        let bestText = '';
        for (const d of bottomDivs) {
            const t = (d.innerText || '').trim();
            if (t.length > bestLen) { bestLen = t.length; bestText = t; }
        }
        if (bestLen > 200) {
            body = bestText;
        } else {
            // Fallback: use the full main-inner text and strip header
            const full = (bodyEl.innerText || '').trim();
            // Try to start from "Grammy" or whatever - find first capital sentence after the byline
            body = full;
        }
    }
    // Clean up: remove leading "Home » Jazz Articles » ..." breadcrumb
    body = body.replace(/^\\s*Home\\s*».*?Album Review\\s*»\\s*/i, '');
    // Collapse whitespace
    body = body.replace(/\\s+/g, ' ').trim();
    return {
        body: body,
        title: (document.querySelector('h1') || {}).textContent || '',
    };
}
"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape All About Jazz reviews")
    parser.add_argument("--pages", type=int, default=2, help="Number of listing pages (max 2 per spec)")
    parser.add_argument("--days", type=float, default=1.5, help="Max age in days (default 1.5 = 36h)")
    parser.add_argument("--date", type=str, default=None, help="Explicit cutoff date YYYY-MM-DD")
    parser.add_argument("--no-article-pages", action="store_true", help="Skip visiting individual article pages")
    args = parser.parse_args()
    pages = min(args.pages, 2)

    now = datetime.now(timezone.utc)
    if args.date:
        cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        cutoff_date = (now - timedelta(days=args.days)).date()
    cutoff_iso = cutoff_date.isoformat()

    sys.stderr.write(
        f"AAJ scraper — Now: {now.isoformat()}, Cutoff: {cutoff_iso}, Pages: {pages}\n"
    )

    tab_resp = _api("POST", "/tabs", {
        "userId": USER_ID,
        "sessionKey": SESSION_KEY,
        "url": LIST_URL,
    })
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        result = {"meta": {"total": 0, "scraped_at": now.isoformat(), "cutoff_date": cutoff_iso}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    all_items = []
    try:
        time.sleep(2)

        # ── Step 1: Collect cards from listing pages ─────────────────────
        all_cards = []
        seen_urls = set()
        for page_num in range(1, pages + 1):
            sys.stderr.write(f"\n=== Page {page_num} ===\n")
            if page_num == 1:
                # Already navigated on tab creation
                pass
            else:
                page_url = f"{LIST_URL}&pg={page_num}"
                _api("POST", f"/tabs/{tab_id}/navigate", {"url": page_url})
                time.sleep(2)

            resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                "expression": EXTRACT_CARDS_JS,
            })
            cards = resp.get("result") or []
            sys.stderr.write(f"Found {len(cards)} cards on page {page_num}\n")
            for c in cards:
                url = c.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_cards.append(c)

        sys.stderr.write(f"\nTotal unique cards: {len(all_cards)}\n")

        # ── Step 2: Date filter + normalize ─────────────────────────────
        kept = []
        for c in all_cards:
            url = c.get("url", "")
            if url.startswith("/"):
                url = BASE_URL + url
            elif url.startswith("//"):
                url = "https:" + url

            album = (c.get("album") or "").strip()
            artist = (c.get("artist") or "").strip()
            date_text = c.get("date_text", "")
            score = c.get("score")

            # Non-music filter
            combined = f"{artist} {album}"
            if NON_MUSIC_RE.search(combined):
                sys.stderr.write(f"  SKIP (non-music): {artist} - {album}\n")
                continue

            # Parse date
            pub_date = parse_listing_date(date_text) or ""
            if not pub_date:
                sys.stderr.write(f"  SKIP (no date): {artist} - {album}\n")
                continue
            try:
                item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
            except ValueError:
                continue
            if item_date < cutoff_date:
                sys.stderr.write(f"  SKIP (out of window {pub_date}): {artist} - {album}\n")
                continue

            kept.append({
                "album": album,
                "artist": artist,
                "score": score,
                "url": url,
                "source": SOURCE,
                "pub_date": pub_date,
                "tags": TAGS_DEFAULT,
                "excerpt": "",
                "body": "",
                "site_id": SITE_ID,
                "crawl_status": "pending",
                "type": "review",
            })

        sys.stderr.write(f"Items in 36h window: {len(kept)}\n")

        # ── Step 3: Visit each article for full body ────────────────────
        if not args.no_article_pages and kept:
            sys.stderr.write(f"\n=== Visiting {len(kept)} articles for body text ===\n")
            for i, item in enumerate(kept):
                url = item["url"]
                sys.stderr.write(f"  [{i+1}/{len(kept)}] {item['artist'] or '?'} : {item['album'][:50]}\n")
                try:
                    _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                    time.sleep(1.2)
                    resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                        "expression": EXTRACT_BODY_JS,
                    })
                    detail = resp.get("result") or {}
                    body = (detail.get("body") or "").strip()
                    if body:
                        item["body"] = body
                        item["excerpt"] = body[:500]
                        item["crawl_status"] = "success"
                    else:
                        item["crawl_status"] = "empty"
                    sys.stderr.write(f"    body: {len(body)} chars\n")
                except Exception as e:
                    sys.stderr.write(f"    ERROR: {e}\n")
                    item["crawl_status"] = "partial"
                    if not item.get("excerpt"):
                        item["excerpt"] = f"(Visit URL for full review: {url})"
        else:
            for item in kept:
                item["crawl_status"] = "skipped"

        all_items = kept

        # ── Step 4: Output ──────────────────────────────────────────────
        result = {
            "meta": {
                "total": len(all_items),
                "scraped_at": now.isoformat(),
                "cutoff_date": cutoff_iso,
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
