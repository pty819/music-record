#!/usr/bin/env python3
"""
scrape_sea_of_tranquility.py — Camoufox-based scraper for Sea of Tranquility reviews.

Extracts recent album reviews from https://www.seaoftranquility.org.
The site is an old PHP/table-based site. Strategy:

  1. POST /tabs to create a tab and navigate to the reviews index page
     (https://www.seaoftranquility.org/reviews.php)
  2. Extract the 100 most recent review links (op=showcontent&id=NNNNN)
  3. For each review link, navigate to the review page and extract:
     - Title (in "Artist: Album" or "Artist - Album" format)
     - Date from "Added: ..." metadata line
     - Score from star images (star_whole.gif=1, star_half.gif=0.5)
     - Full body text from the review page
     - Excerpt from first paragraph of review body
  4. Close the tab via DELETE /tabs/{tabId}
  5. Output structured JSON to stdout

Output format:
  {"meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."}, "items": [
    {album, artist, score, url, source, pub_date, tags, excerpt, body, site_id, crawl_status, type}
  ]}

Usage:
  python3 scrape_sea_of_tranquility.py [--limit N] [--days 2] [--date YYYY-MM-DD]
"""

import json
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from html import unescape

import urllib.request
import urllib.error

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
INDEX_URL = "https://www.seaoftranquility.org/reviews.php"
BASE_URL = "https://www.seaoftranquility.org"

SITE_ID = "sea_of_tranquility"
SOURCE = "Sea of Tranquility"
TAGS = "progressive rock,progressive metal"
USER_ID = "scraper_sea_of_tranquility"
SESSION_KEY = "session_sot"

# JS to get full body text from a review page
GET_BODY_JS = """
() => {
    const article = document.querySelector('article');
    if (article) return article.innerText.slice(0, 10000);
    return document.body.innerText.slice(0, 10000);
}
"""

# Date from index page — "May 21st 2026", "May 21, 2026", "5/21/2026"
DATE_ADDED_PATTERN = re.compile(
    r"Added:\s*(.+?)(?:<|$)"
)
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
ORD_SUFFIX = re.compile(r"(st|nd|rd|th)")


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
        body_text = e.read().decode()[:500]
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {body_text}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


def parse_added_date(text: str) -> str | None:
    """Parse date string like 'May 21st 2026' or 'May 21, 2026' into ISO date."""
    text = text.strip()
    # Remove ordinal suffixes: 21st -> 21, 2nd -> 2, 3rd -> 3
    text = ORD_SUFFIX.sub("", text)
    # Try various formats
    for fmt in ["%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"]:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    # Try manual parsing
    parts = text.replace(",", "").split()
    if len(parts) >= 3:
        month_name = parts[0].lower()
        day_str = parts[1]
        year_str = parts[2]
        month = MONTHS.get(month_name)
        if month and day_str.isdigit() and year_str.isdigit():
            try:
                dt = datetime(int(year_str), month, int(day_str))
                return dt.date().isoformat()
            except ValueError:
                pass
    return None


def parse_star_score(html_snippet: str) -> float | None:
    """Count star images: star_whole.gif = 1.0, star_half.gif = 0.5.
    Returns total score out of 5."""
    wholes = html_snippet.count("star_whole.gif")
    halves = html_snippet.count("star_half.gif")
    total = wholes + (halves * 0.5)
    if total == 0:
        return None
    return total


def parse_artist_album(title: str) -> tuple:
    """
    Split title into (artist, album).

    Most titles are "Artist: Album" format.
    Some use "Artist - Album" format.
    Some are just "Album" with no artist.
    Some use "Lastname, Firstname: Album" format.
    """
    title = title.strip()
    # Try colon first (most common): "Artist: Album"
    if ": " in title:
        parts = title.split(": ", 1)
        artist = parts[0].strip()
        album = parts[1].strip()
        # Handle "Lastname, Firstname" -> "Firstname Lastname" format
        # e.g. "Hampton, Michael: Into the Public Domain" -> Michael Hampton
        # But also legitimate comma use in band names like "Selecter, The"
        if "," in artist and not artist.lower().startswith("the "):
            # Could be "Last, First" format — check if second part is short
            name_parts = artist.split(",", 1)
            possible_first = name_parts[1].strip()
            possible_last = name_parts[0].strip()
            # If the "last name" part is a single word, it's likely "Last, First"
            if len(possible_last.split()) == 1 and len(possible_first.split()) <= 3:
                artist = f"{possible_first} {possible_last}"
        return artist, album

    # Try dash: "Artist - Album" 
    m = re.match(r"^(.+?)\s*[—–-]\s*(.+)$", title)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # No separator found — entire title is album, unknown artist
    return "", title


# ── JS that extracts review index links ──────────────────────────────────

EXTRACT_INDEX_LINKS_JS = """
() => {
    const links = document.querySelectorAll("a[href*='reviews.php?op=showcontent&id=']");
    return Array.from(links).map(a => ({
        title: a.textContent.trim().replace(/\\\\u00a0/g, ' ').replace(/\\\\u2020/g, '').trim(),
        href: a.href,
        id: (a.href.match(/id=(\\\\d+)/) || [])[1] || ''
    }));
}
"""

# ── JS that extracts review detail page data ────────────────────────────

EXTRACT_REVIEW_JS = """
() => {
    const body = document.body;

    // Extract title from <font> with <b>
    const titleEl = document.querySelector('font[size="4"] b') ||
                    document.querySelector('font[size="4"] i b');
    let title = '';
    if (titleEl) {
        title = titleEl.textContent.trim();
    } else {
        // Fallback: look for <b> in the content's <td>
        const tds = document.querySelectorAll('td');
        for (const td of tds) {
            const b = td.querySelector('b');
            if (b && b.textContent.includes(':')) {
                title = b.textContent.trim();
                break;
            }
        }
    }

    // Extract metadata - find the blockquote or td near "Added:"
    const html = document.body.innerHTML;
    const addedIdx = html.indexOf('<b>Added:');
    let addedDate = '';
    let scoreHtml = '';
    if (addedIdx >= 0) {
        const block = html.substring(addedIdx, addedIdx + 800);
        // Date: <b>Added:</b> May 21st 2026<br>
        const dateMatch = block.match(/<b>Added:<\\/b>\\s*([^<]+?)(?:<|$)/);
        if (dateMatch) {
            addedDate = dateMatch[1].trim();
        }
        // Score block
        const scoreStart = block.indexOf('<b>Score:');
        if (scoreStart >= 0) {
            const scoreEnd = block.indexOf('<br', scoreStart);
            if (scoreEnd >= 0) {
                scoreHtml = block.substring(scoreStart, scoreEnd + 4);
            } else {
                scoreHtml = block.substring(scoreStart, Math.min(scoreStart + 300, block.length));
            }
        }
    }

    // Extract review text (excerpt) — first paragraph of actual review
    // Find paragraph after the title but before Track Listing / Added:
    let excerpt = '';
    const pElements = document.querySelectorAll('p[align="justify"]');
    if (pElements.length > 0) {
        // First justified paragraph is usually the start of the review
        excerpt = pElements[0].textContent.trim();
    }
    if (!excerpt) {
        // Fallback: try blockquote p
        const bq = document.querySelector('blockquote');
        if (bq) {
            const firstP = bq.querySelector('p');
            if (firstP) {
                excerpt = firstP.textContent.trim();
            }
        }
    }

    return {
        title: title,
        added_date: addedDate,
        score_html: scoreHtml,
        excerpt: excerpt
    };
}
"""


# ── Main ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Sea of Tranquility reviews"
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Max reviews to scrape (default: 100, max from index page)"
    )
    parser.add_argument(
        "--days", type=float, default=1.5,
        help="Max age in days for articles (default: 2)"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Explicit cutoff date (YYYY-MM-DD). Overrides --days."
    )
    args = parser.parse_args()
    limit = min(args.limit, 100)

    today = datetime.now(timezone.utc).date()
    if args.date:
        try:
            cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.stderr.write(f"ERROR: Invalid --date format '{args.date}'. Use YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        cutoff_date = today - timedelta(days=args.days)

    sys.stderr.write(
        f"Sea of Tranquility scraper — Today: {today}, Cutoff: {cutoff_date}, "
        f"Limit: {limit}, Days: {args.days}\n"
    )

    # Step 1: Create tab and go to reviews index
    sys.stderr.write(f"Creating tab and navigating to {INDEX_URL}...\n")
    tab_resp = _api("POST", "/tabs", {
        "userId": USER_ID,
        "sessionKey": SESSION_KEY,
        "url": INDEX_URL,
    })
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        result = {"meta": {"total": 0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    all_items = []

    try:
        # Step 2: Wait a moment then extract review links from index page
        import time
        time.sleep(1)
        sys.stderr.write("Extracting review links from index page...\n")
        links_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "expression": EXTRACT_INDEX_LINKS_JS,
        })
        raw_links = links_resp.get("result") or []
        sys.stderr.write(f"Found {len(raw_links)} review links\n")

        # Step 3: Visit each review page
        for i, link in enumerate(raw_links):
            if i >= limit:
                break

            review_url = link.get("href", "")
            idx_title = link.get("title", "")
            review_id = link.get("id", "")

            if not review_url:
                continue

            sys.stderr.write(
                f"  [{i+1}/{min(len(raw_links), limit)}] "
                f"Scraping review #{review_id}: {idx_title[:60]}...\n"
            )

            try:
                # Navigate to review page
                _api("POST", f"/tabs/{tab_id}/navigate", {
                    "url": review_url,
                })
                time.sleep(1)

                # Extract review data
                detail_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                    "expression": EXTRACT_REVIEW_JS,
                })
                detail = detail_resp.get("result") or {}

                title = detail.get("title", "") or idx_title
                added_date_str = detail.get("added_date", "")
                score_html = detail.get("score_html", "")
                excerpt = detail.get("excerpt", "")

                # Fetch full body text
                body_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                    "expression": GET_BODY_JS,
                })
                body = str(body_resp.get("result", "") or "").strip()[:10000]

                # Parse score from star images
                score = parse_star_score(score_html)

                # Parse date
                pub_date = None
                if added_date_str:
                    pub_date = parse_added_date(added_date_str)

                # Parse artist/album from title
                artist, album = parse_artist_album(title)

                # If empty, use the index page title
                if not album:
                    artist, album = parse_artist_album(idx_title)

                # Apply cutoff filter
                if pub_date:
                    try:
                        item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                        if item_date < cutoff_date:
                            sys.stderr.write(f"    SKIP — before cutoff ({pub_date})\n")
                            continue
                    except ValueError:
                        pass

                # Extract first ~500 chars of excerpt, clean HTML entities
                if excerpt:
                    excerpt = unescape(excerpt)[:500]

                item = {
                    "album": album,
                    "artist": artist,
                    "score": score,
                    "url": review_url,
                    "source": SOURCE,
                    "pub_date": pub_date or today.isoformat(),
                    "tags": TAGS,
                    "excerpt": (excerpt or body)[:500],
                    "body": body,
                    "site_id": SITE_ID,
                    "crawl_status": "success",
                    "type": "review",
                }
                all_items.append(item)

                sys.stderr.write(
                    f"    OK — {artist or '?'} : {album or title[:40]}"
                    f" ({pub_date or '?'}, score={score}, body: {len(body)} chars)\n"
                )

            except Exception as e:
                sys.stderr.write(
                    f"    ERROR scraping {review_url}: {e}\n"
                )
                all_items.append({
                    "album": idx_title or "",
                    "artist": "",
                    "score": None,
                    "url": review_url,
                    "source": SOURCE,
                    "pub_date": today.isoformat(),
                    "tags": TAGS,
                    "excerpt": "",
                    "body": "",
                    "site_id": SITE_ID,
                    "crawl_status": "error",
                    "type": "review",
                })

        # Step 4: Build output
        result = {
            "meta": {
                "total": len(all_items),
                "scraped_at": today.isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
            },
            "items": all_items,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.stderr.write(f"Total: {len(all_items)} reviews\n")

    finally:
        # Step 5: Always close the tab
        try:
            _api("DELETE", f"/tabs/{tab_id}")
            sys.stderr.write(f"Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"WARNING: Failed to close tab: {e}\n")


if __name__ == "__main__":
    main()
