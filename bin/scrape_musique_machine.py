#!/usr/bin/env python3
"""
scrape_musique_machine.py — Camoufox-based scraper for Musique Machine.

Extracts album reviews from https://www.musiquemachine.com homepage,
then fetches the full article body from each review's individual page.
The site is Next.js-based and renders content client-side, so we use
the Camoufox headless browser REST API to evaluate JS in the page context.

Strategy:
  1. POST /tabs to create a tab and navigate to the homepage
  2. Evaluate JS that queries the DOM for review cards under "Latest Reviews"
  3. Extract: title (Artist — Album), date, rating (from aria-label), excerpt, URL
  4. For each review, navigate to the article URL and evaluate JS to get full body
  5. Filter to reviews published within the last N days
  6. Close the tab via DELETE /tabs/{tabId}
  7. Output structured JSON to stdout

Output format:
  {"meta": {"total": N}, "items": [
    {album, artist, score, url, source, pub_date, tags, excerpt, body, site_id, crawl_status, type}
  ]}

Usage:
  python3 scrape_musique_machine.py                              # last 2 days
  python3 scrape_musique_machine.py --days 7                     # last 7 days
  python3 scrape_musique_machine.py --date 2026-05-24            # specific date
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta

import urllib.request
import urllib.error

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
TARGET_URL = "https://www.musiquemachine.com"
TODAY = datetime.now(timezone.utc).date()

SITE_ID = "musique_machine"
SOURCE = "Musique Machine"
TAGS = "experimental,industrial,noise"
USER_ID = "scraper_musique_machine"
SESSION_KEY = "session_mm"

DATE_PATTERN = re.compile(r"(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})")
TITLE_SEP_PATTERN = re.compile(r"\s*[—–-]\s*")

# ── Helpers ────────────────────────────────────────────────────────────


def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Make a JSON API call to the Camoufox REST server."""
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


def parse_date(text: str) -> tuple:
    """Parse '25 May 2026' format date. Returns (date_obj, iso_string) or (None, '')."""
    text = text.strip()
    m = DATE_PATTERN.match(text)
    if not m:
        return None, ""
    try:
        dt = datetime.strptime(m.group(0), "%d %B %Y")
        return dt.date(), dt.date().isoformat()
    except ValueError:
        pass
    try:
        dt = datetime.strptime(m.group(0), "%d %b %Y")
        return dt.date(), dt.date().isoformat()
    except ValueError:
        return None, ""


def extract_artist_album(title: str) -> tuple:
    """Split 'ARTIST — ALBUM' into (artist, album)."""
    title = title.strip()
    m = TITLE_SEP_PATTERN.split(title, maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()
    # No separator found — treat entire title as album, unknown artist
    return "", title


def extract_reviews_from_dom(html_or_text: str) -> list:
    """
    Fallback: parse reviews from innerText of the page body.
    Used only if the DOM extraction JS fails.
    """
    return []


# ── JS expressions ─────────────────────────────────────────────────────

EXTRACT_REVIEWS_JS = """
() => {
    const results = [];

    // Find the "Latest Reviews" section
    const sections = document.querySelectorAll('section');
    let targetSection = null;
    for (const section of sections) {
        const h2 = section.querySelector('h2');
        if (h2 && h2.textContent.trim().toLowerCase() === 'latest reviews') {
            targetSection = section;
            break;
        }
    }
    if (!targetSection) return results;

    // Find all review card links within the grid
    const cards = targetSection.querySelectorAll('a[href*="/reviews/"]');
    for (const card of cards) {
        // Rating: from aria-label on the rating span
        const ratingSpan = card.querySelector('[aria-label]');
        let score = null;
        if (ratingSpan) {
            const label = ratingSpan.getAttribute('aria-label') || '';
            const m = label.match(/Rating:\\s*(\\d+)\\s*out\\s*of\\s*5/i);
            if (m) score = parseInt(m[1], 10);
        }

        // Date: from span with tracking-wider classes
        const dateSpan = card.querySelector('span.tracking-wider');
        let dateText = '';
        if (dateSpan) {
            dateText = dateSpan.textContent.trim();
        }

        // Title: from h3
        const h3 = card.querySelector('h3');
        let title = '';
        if (h3) {
            title = h3.textContent.trim();
        }

        // Excerpt: from p with line-clamp
        const excerptP = card.querySelector('p');
        let excerpt = '';
        if (excerptP) {
            excerpt = excerptP.textContent.trim();
        }

        // URL
        const href = card.getAttribute('href') || '';
        const fullUrl = href.startsWith('http') ? href : 'https://www.musiquemachine.com' + href;

        results.push({
            title: title,
            date_text: dateText,
            score: score,
            excerpt: excerpt,
            url: fullUrl,
        });
    }
    return results;
}
"""

FETCH_ARTICLE_BODY_JS = """() => {
    const article = document.querySelector('article');
    if (article) {
        return article.innerText.slice(0, 10000);
    }
    return document.body.innerText.slice(0, 10000);
}
"""


# ── Main ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Musique Machine reviews."
    )
    parser.add_argument(
        "--days",
        type=float,
        default=1.5,
        help="Number of days back to include (default: 2)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Specific date YYYY-MM-DD to filter reviews (overrides --days)",
    )
    args = parser.parse_args()

    if args.date:
        try:
            cutoff = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.stderr.write(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        cutoff = TODAY - timedelta(days=args.days)

    sys.stderr.write(
        f"Musique Machine scraper — Today: {TODAY}, Cutoff: {cutoff}\n"
    )

    # Step 1: Create tab and navigate to homepage
    sys.stderr.write(f"Creating tab and navigating to {TARGET_URL}...\n")
    tab_resp = _api("POST", "/tabs", {
        "userId": USER_ID,
        "sessionKey": SESSION_KEY,
        "url": TARGET_URL,
    })
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        result = {"meta": {"total": 0}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    try:
        # Step 2: Evaluate JS to extract review data from the DOM
        sys.stderr.write("Evaluating JS to extract review cards...\n")
        eval_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "expression": EXTRACT_REVIEWS_JS,
        })

        raw_reviews = eval_resp.get("result", [])
        if raw_reviews is None:
            raw_reviews = []

        sys.stderr.write(f"Found {len(raw_reviews)} raw review entries\n")

        # Step 3: Parse each review
        items = []
        for raw in raw_reviews:
            title = raw.get("title", "")
            date_text = raw.get("date_text", "")
            score = raw.get("score")
            excerpt = raw.get("excerpt", "")
            url = raw.get("url", "")

            # Skip entries without a proper title or date
            if not title or not date_text:
                continue

            # Parse date
            pub_date_obj, pub_date = parse_date(date_text)
            if not pub_date_obj:
                sys.stderr.write(f"  SKIP — unparseable date '{date_text}': {title[:50]}\n")
                continue

            # Filter by cutoff
            if not (cutoff <= pub_date_obj <= TODAY):
                sys.stderr.write(f"  SKIP — date {pub_date} out of range: {title[:50]}\n")
                continue

            # Extract artist and album from title
            artist, album = extract_artist_album(title)

            items.append({
                "album": album,
                "artist": artist,
                "score": score,
                "url": url,
                "source": SOURCE,
                "pub_date": pub_date,
                "tags": TAGS,
                "excerpt": excerpt[:500],
                "body": None,  # Will be filled in below
                "site_id": SITE_ID,
                "crawl_status": "success",
                "type": "review",
            })

            sys.stderr.write(
                f"  OK — {artist or '?'} : {album or title[:40]} "
                f"({pub_date}, score={score})\n"
            )

        # Step 4: Fetch full article body for each review
        sys.stderr.write(f"Fetching full article bodies for {len(items)} items...\n")
        for idx, item in enumerate(items, 1):
            if not item["url"]:
                item["body"] = ""
                continue

            sys.stderr.write(f"  [{idx}/{len(items)}] Navigating to: {item['url']}\n")

            try:
                # Navigate to the article page
                nav_resp = _api("POST", f"/tabs/{tab_id}/navigate", {
                    "url": item["url"],
                })
                if nav_resp.get("success") or nav_resp.get("tabId"):
                    # Brief wait for JS rendering
                    import time
                    time.sleep(2)

                    # Evaluate JS to get article body
                    body_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                        "expression": FETCH_ARTICLE_BODY_JS,
                    })
                    body_text = body_resp.get("result", "")
                    if body_text:
                        item["body"] = body_text.strip()
                        sys.stderr.write(f"    Body: {len(item['body'])} chars\n")
                    else:
                        item["body"] = ""
                        sys.stderr.write(f"    No body returned\n")
                else:
                    sys.stderr.write(f"    Navigation failed: {nav_resp}\n")
                    item["body"] = ""
            except Exception as e:
                sys.stderr.write(f"    Error fetching body: {e}\n")
                item["body"] = ""

        # Step 5: Build output
        result = {
            "meta": {
                "total": len(items),
            },
            "items": items,
        }

        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.stderr.write(f"Total: {len(items)} reviews\n")

    finally:
        # Step 6: Always close the tab
        try:
            _api("DELETE", f"/tabs/{tab_id}")
            sys.stderr.write(f"Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"WARNING: Failed to close tab: {e}\n")


if __name__ == "__main__":
    main()
