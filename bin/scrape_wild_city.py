#!/usr/bin/env python3
"""
scrape_wild_city.py — Camoufox-based scraper for Wild City.

Extracts album/artist reviews from https://www.thewildcity.com.
Reviews are in the Features section with "Review:" prefix in the title.
The site uses a custom CMS (Mamoka Boilerplate) and renders content server-side,
but we use the Camoufox headless browser REST API for consistent evaluation.

Strategy:
  1. POST /tabs to create a tab and navigate to the homepage
  2. Evaluate JS that collects all items from the sidebar feed (has data-date="DD/MM/YYYY")
     and all stripe/box items with "Review:" in the title
  3. Navigate to /features and /features?offset=10 for more review items
  4. Cross-reference review items with feed items by URL to get dates
  5. For each review, navigate to its article URL and fetch full body text
  6. Extract: title (parsed for artist/album), date, excerpt, body, URL
  7. Close tabs
  8. Output structured JSON to stdout

Output format:
  {"meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."}, "items": [
    {album, artist, score (None), url, source='Wild City', pub_date (ISO or ''),
     tags='indie,electronic,india', excerpt (first 500 of body), body (full),
     site_id='wild_city', crawl_status='success', type='review'}
  ]}

Usage:
  python3 scrape_wild_city.py [--days 2] [--date YYYY-MM-DD]
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
TARGET_URL = "https://www.thewildcity.com"
FEATURES_URL = "https://www.thewildcity.com/features"
FEATURES_P2_URL = "https://www.thewildcity.com/features?offset=10"

SITE_ID = "wild_city"
SOURCE = "Wild City"
TAGS = "indie,electronic,india"
USER_ID = "scraper_wild_city"
SESSION_KEY = "session_wc"

# Regex for dd/mm/yyyy dates
DATE_PATTERN = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
# Title separator: " — " or " – "
TITLE_SEP_PATTERN = re.compile(r"\s*[—–-]\s*")

# JS to get full body text from an article page
GET_BODY_JS = """
() => {
    const article = document.querySelector('article');
    if (article) return article.innerText.slice(0, 10000);
    return document.body.innerText.slice(0, 10000);
}
"""

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
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


def close_tab(tab_id: str):
    """Safely close a Camoufox tab."""
    if tab_id:
        try:
            _api("DELETE", f"/tabs/{tab_id}")
            sys.stderr.write(f"  Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"  WARNING: Failed to close tab: {e}\n")


def create_tab(url: str) -> str | None:
    """Create a Camoufox tab and navigate to URL. Returns tab_id or None."""
    sys.stderr.write(f"  Creating tab for {url[:80]}...\n")
    try:
        tab_resp = _api("POST", "/tabs", {
            "userId": USER_ID,
            "sessionKey": SESSION_KEY,
            "url": url,
        })
        tab_id = tab_resp.get("tabId")
        if not tab_id:
            sys.stderr.write("  ERROR: No tabId in response\n")
            return None
        # Wait for page to render (site is slow, 30-60s)
        sys.stderr.write(f"  Tab {tab_id} created, waiting for page load...\n")
        time.sleep(10)
        return tab_id
    except Exception as e:
        sys.stderr.write(f"  ERROR creating tab: {e}\n")
        return None


def evaluate_js(tab_id: str, expression: str) -> list:
    """Evaluate JS expression in a Camoufox tab. Returns result list or []."""
    try:
        eval_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "expression": expression,
        })
        result = eval_resp.get("result", [])
        if result is None:
            return []
        return result
    except Exception as e:
        sys.stderr.write(f"  ERROR evaluating JS: {e}\n")
        return []


def evaluate_js_text(tab_id: str, expression: str) -> str:
    """Evaluate JS expression returning a string."""
    try:
        eval_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "expression": expression,
        })
        result = eval_resp.get("result", "")
        if result is None:
            return ""
        return str(result)
    except Exception as e:
        sys.stderr.write(f"  ERROR evaluating JS: {e}\n")
        return ""


def navigate(tab_id: str, url: str):
    """Navigate an existing tab to a new URL."""
    try:
        _api("POST", "/tabs", {
            "userId": USER_ID,
            "sessionKey": SESSION_KEY,
            "url": url,
            "tabId": tab_id,
        })
        sys.stderr.write(f"  Navigated to {url[:80]}...\n")
        time.sleep(10)
    except Exception as e:
        sys.stderr.write(f"  ERROR navigating tab: {e}\n")


def fetch_body(tab_id: str) -> str:
    """Fetch full body text from the current page via JS evaluation."""
    try:
        result = evaluate_js_text(tab_id, GET_BODY_JS)
        return result.strip()[:10000]
    except Exception as e:
        sys.stderr.write(f"  ERROR fetching body: {e}\n")
        return ""


def parse_date_dd_mm_yyyy(text: str) -> str:
    """Parse 'DD/MM/YYYY' format date. Returns ISO string or ''."""
    text = text.strip()
    m = DATE_PATTERN.match(text)
    if not m:
        return ""
    try:
        dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return dt.date().isoformat()
    except ValueError:
        return ""


def extract_artist_album(title: str) -> tuple:
    """Extract (artist, album) from a Wild City review title.

    Wild City review title patterns (after stripping "Review:"):
      "ARTIST Finds A Friend... On Debut Mixtape 'ALBUM'"
      "On 'ALBUM', ARTIST Keeps Dubstep Political..."
      "ARTIST's Sophomore Album 'ALBUM' Bridges..."
      "ARTIST Presents 'ALBUM'..."
      "'ALBUM' Marks a Milestone... for ARTIST"
      "'ALBUM' Presents A Love Letter To..."
      "KALI Sees Ditty Blending Protest..."  (Kali = album, Ditty = artist)

    Strategy:
      - Find album in quotes (handling apostrophes inside: 'Babylon's Camp')
      - For artist: possessive name, text before quoted album
      - Falls back gracefully to empty artist / full title as album
    """
    title = title.strip()
    if title.lower().startswith("review:"):
        title = title[7:].strip()
    elif title.lower().startswith("review — "):
        title = title[9:].strip()
    title = title.strip()

    # Find album in quotes — handle apostrophes inside by using lookbehind/
    # lookahead to ensure ' is a quote delimiter, not an apostrophe (e.g., 'Babylon's Camp')
    # Smart quotes (\u2018\u2019) are also used as apostrophes in "Collective's"
    album = ""
    artist = ""
    quote_pairs = [
        # Smart quotes: \u2018...\u2019. But \u2019 is also used as apostrophe
        # inside titles (e.g. "Babylon\u2019s Camp"). Allow \u2019 inside the
        # match when it's followed by a word char (apostrophe usage).
        (r"\u2018((?:[^\u2018\u2019]|\u2019(?=\w))+?)\u2019(?=\s|,|\.|!|\?|$)", "single-smart"),
        (r"\u201c((?:[^\u201c\u201d]|\u201d(?=\w))+?)\u201d(?=\s|,|\.|!|\?|$)", "double-smart"),
        # ASCII ' — same logic: allow ' inside when followed by word char
        (r"(?:^|\s|,)\x27((?:[^\x27]|\x27(?=\w))+?)\x27(?=\s|,|\.|!|\?|$)", "single-ascii"),
        (r"\x22((?:[^\x22]|\x22(?=\w))+?)\x22", "double-ascii"),
    ]

    album_start = -1
    album_end = -1

    for pattern, kind in quote_pairs:
        for m in re.finditer(pattern, title):
            candidate = m.group(1).strip()
            # Skip if it's just a single letter/possessive marker
            if len(candidate) < 2:
                continue
            # Prefer the longest candidate (most likely actual album title)
            if len(candidate) > len(album):
                album = candidate
                album_start = m.start()
                album_end = m.end()

    # If no album found in quotes, try possessive pattern
    if not album:
        # Check for "ARTIST's SOMETHING" possessive
        poss_match = re.search(r"^(.+?)'s\s+(.+?)(?:\s+(?:bridges|marks|sees|is|has|makes|showcases|infuses|returns))", title)
        if poss_match:
            artist = poss_match.group(1).strip()
            album_candidate = poss_match.group(2).strip()
            # Filter out generic words
            if album_candidate.lower() not in ("sophomore", "debut", "new", "latest"):
                album = album_candidate
            else:
                # Look for "Sophomore Album/EP/LP/Mixtape/Single 'ALBUM'"
                sub_match = re.search(r"(?:sophomore\s+)?(?:album|debut|ep|mixtape|single|lp)\s+['\u2018\u2019](.+?)['\u2018\u2019]", title[poss_match.end():])
                if sub_match:
                    album = sub_match.group(1).strip()
                else:
                    # Just take the first meaningful phrase
                    album = album_candidate
        else:
            # No quotes, no possessive — use whole title
            album = title
        return artist.strip(), album.strip()

    # ── Extract artist ──
    before = title[:album_start].strip().rstrip(",").strip()
    after = title[album_end:].strip().lstrip(",").strip()

    if not before or len(before) < 3:
        # Pattern: "'ALBUM' VERB/Presents/..." — album leads, no artist
        # or: "'ALBUM', ARTIST..." — artist is after the comma
        # Check for "by ARTIST" in the after text
        by_match = re.search(r"\bby\s+(.+?)$", after, re.IGNORECASE)
        if by_match:
            artist = by_match.group(1).strip()
        # Check for "On 'ALBUM', ARTIST" pattern
        elif re.match(r"on\s+", before, re.IGNORECASE) or after.startswith(","):
            after_clean = after.lstrip(",").strip()
            # First significant word(s) = artist
            artist = after_clean.split()[0] if after_clean else ""
        else:
            artist = ""
    elif before.lower().startswith("on "):
        # "On 'ALBUM', ARTIST..."
        if not before[3:].strip() or before[3:].strip() == "on":
            # Artist is after the quote
            # Just take first few words
            after_clean = after.lstrip(",").strip()
            artist = re.split(
                r"\s+(?:keeps|finds|bridges|marks|sees|doesn|does|presents|is|has|makes|returns|turns)",
                after_clean, maxsplit=1, flags=re.IGNORECASE
            )[0].strip().rstrip(",")
        else:
            artist = before[3:].strip()
    else:
        # Text before the album contains potential artist name
        # Check for possessive (handles both ASCII ' and Unicode ')
        poss_found = False
        for poss_char in ["\u2019", "'", "\u2018"]:
            # Check for possessive 's anywhere in before text, not just at end
            # (e.g. "Gauley Bhai\u2019s Sophomore Album")
            poss_pattern = rf"{re.escape(poss_char)}s(?:\s|$)"
            if re.search(poss_pattern, before):
                artist = re.sub(poss_pattern, " ", before).strip()
                poss_found = True
                break
        if not poss_found:
            # Try to split on common verbs
            artist = re.split(
                r"\s+(?:finds|doesn|does|bridges|marks|presents|sees|"
                r"keeps|returns|turns|steps|infuses|makes|aims|flips|"
                r"mixes|introduces|comes|launches)\b",
                before, maxsplit=1, flags=re.IGNORECASE
            )[0].strip()
            # Clean trailing words
            artist = re.sub(
                r"\s+(?:on|with|for|the|their|his|her|a|an|to)\s*$",
                "", artist, flags=re.IGNORECASE
            ).strip()

    # Clean up
    artist = artist.strip().strip(",").strip("'\"")
    album = album.strip().strip(",").strip("'\u2018\u2019\u201c\u201d")

    # Strip known descriptor phrases from artist name
    artist = re.sub(
        r"\s+(?:sophomore\s+)?(?:album|debut|ep|mixtape|single|lp|new|latest)\s*$",
        "", artist, flags=re.IGNORECASE
    ).strip()

    # Validate: artist shouldn't be a verb from our list
    noisy_artists = {"finds", "doesn", "does", "bridges", "marks", "presents",
                     "sees", "keeps", "returns", "turns", "steps", "infuses",
                     "makes", "aims", "flips", "mixes", "introduces", "comes",
                     "launches", "on"}
    if artist.lower() in noisy_artists:
        artist = ""

    return artist.strip(), album.strip()


# ── JS extraction expressions ──────────────────────────────────────────

# Extract sidebar feed items with their data-date
EXTRACT_FEED_JS = """
() => {
    const feedItems = document.querySelectorAll('.feed .box, .box[data-date]');
    const results = [];
    const seen = new Set();
    for (const item of feedItems) {
        const href = item.getAttribute('href') || '';
        if (!href || seen.has(href)) continue;
        seen.add(href);
        const date = item.getAttribute('data-date') || '';
        const title = item.querySelector('p, .title, h3');
        const titleText = title ? title.textContent.trim() : '';
        results.push({
            url: href.startsWith('http') ? href : 'https://www.thewildcity.com' + href,
            date: date,
            title: titleText,
        });
    }
    return results;
}
"""

# Extract review items from the main content area (class="stripe")
EXTRACT_REVIEWS_JS = """
() => {
    const results = [];
    // Main content: stripe items that could be reviews
    const stripeItems = document.querySelectorAll('a.stripe');
    for (const item of stripeItems) {
        const href = item.getAttribute('href') || '';
        const h2 = item.querySelector('h2.title');
        const title = h2 ? h2.textContent.trim() : '';
        // Only include items with "Review:" prefix
        if (!title.toLowerCase().startsWith('review:')) continue;
        const p = item.querySelector('p');
        const excerpt = p ? p.textContent.trim() : '';
        results.push({
            url: href.startsWith('http') ? href : 'https://www.thewildcity.com' + href,
            title: title,
            excerpt: excerpt,
        });
    }
    // Also check for box items with Review: prefix on the homepage
    const boxItems = document.querySelectorAll('a.box-big, a.box');
    for (const item of boxItems) {
        const href = item.getAttribute('href') || '';
        const h3 = item.querySelector('h3.title');
        const title = h3 ? h3.textContent.trim() : '';
        if (!title.toLowerCase().startsWith('review:')) continue;
        // Check if we already have this URL
        if (results.some(r => r.url === href)) continue;
        const p = item.querySelector('p');
        const excerpt = p ? p.textContent.trim() : '';
        results.push({
            url: href.startsWith('http') ? href : 'https://www.thewildcity.com' + href,
            title: title,
            excerpt: excerpt,
        });
    }
    return results;
}
"""


# ── Main ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Wild City reviews"
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
        f"Wild City scraper — Today: {today}, Cutoff: {cutoff_date}, "
        f"Days: {args.days}\n"
    )

    # Phase 1: Collect feed items (which have dates) from homepage
    sys.stderr.write("Phase 1: Collecting feed dates from homepage...\n")
    tab_id = create_tab(TARGET_URL)
    if not tab_id:
        result = {"meta": {"total": 0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    feed_by_url = {}  # url -> date string (DD/MM/YYYY)
    all_reviews = {}  # url -> review dict

    try:
        # Extract feed items
        feed_raw = evaluate_js(tab_id, EXTRACT_FEED_JS)
        sys.stderr.write(f"  Found {len(feed_raw)} feed items\n")
        for item in feed_raw:
            url = item.get("url", "")
            date = item.get("date", "")
            if url and date:
                feed_by_url[url] = date

        # Extract reviews from homepage
        reviews_raw = evaluate_js(tab_id, EXTRACT_REVIEWS_JS)
        sys.stderr.write(f"  Found {len(reviews_raw)} reviews on homepage\n")
        for r in reviews_raw:
            url = r.get("url", "")
            if url:
                all_reviews[url] = r

    finally:
        close_tab(tab_id)

    # Phase 2: Visit /features page for more reviews
    sys.stderr.write("Phase 2: Collecting from /features...\n")
    tab_id2 = create_tab(FEATURES_URL)
    if tab_id2:
        try:
            # Extract feed (for dates) and reviews
            feed_raw2 = evaluate_js(tab_id2, EXTRACT_FEED_JS)
            sys.stderr.write(f"  Found {len(feed_raw2)} feed items on /features\n")
            for item in feed_raw2:
                url = item.get("url", "")
                date = item.get("date", "")
                if url and date:
                    feed_by_url[url] = date

            reviews_raw2 = evaluate_js(tab_id2, EXTRACT_REVIEWS_JS)
            sys.stderr.write(f"  Found {len(reviews_raw2)} reviews on /features\n")
            for r in reviews_raw2:
                url = r.get("url", "")
                if url:
                    all_reviews[url] = r
        finally:
            close_tab(tab_id2)

    # Phase 3: Visit /features?offset=10 for page 2
    sys.stderr.write("Phase 3: Collecting from /features page 2...\n")
    tab_id3 = create_tab(FEATURES_P2_URL)
    if tab_id3:
        try:
            feed_raw3 = evaluate_js(tab_id3, EXTRACT_FEED_JS)
            sys.stderr.write(f"  Found {len(feed_raw3)} feed items on /features page 2\n")
            for item in feed_raw3:
                url = item.get("url", "")
                date = item.get("date", "")
                if url and date:
                    feed_by_url[url] = date

            reviews_raw3 = evaluate_js(tab_id3, EXTRACT_REVIEWS_JS)
            sys.stderr.write(f"  Found {len(reviews_raw3)} reviews on /features page 2\n")
            for r in reviews_raw3:
                url = r.get("url", "")
                if url:
                    all_reviews[url] = r
        finally:
            close_tab(tab_id3)

    # Phase 4: Fetch full body for each review by navigating to its URL
    sys.stderr.write(f"\nPhase 4: Fetching full body for {len(all_reviews)} reviews...\n")
    body_tab_id = create_tab(TARGET_URL)
    if not body_tab_id:
        sys.stderr.write("ERROR: Failed to create tab for body fetching\n")
        body_tab_id = None

    items = []
    url_list = list(all_reviews.items())
    for idx, (url, review) in enumerate(url_list):
        title = review.get("title", "")
        excerpt = review.get("excerpt", "")

        if not title:
            continue

        # Get date from feed, fallback to empty
        raw_date = feed_by_url.get(url, "")
        pub_date = parse_date_dd_mm_yyyy(raw_date) if raw_date else ""

        # Apply cutoff filter
        if pub_date:
            try:
                item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                if item_date < cutoff_date:
                    continue
            except ValueError:
                pass

        # Score: not available on Wild City (no star ratings visible)
        score = None

        # Extract artist and album from title
        artist, album = extract_artist_album(title)

        # Fetch full body
        body = ""
        if body_tab_id:
            try:
                navigate(body_tab_id, url)
                body = fetch_body(body_tab_id)
                # Use body text as excerpt if we didn't have one
                if not excerpt and body:
                    excerpt = body[:500]
            except Exception as e:
                sys.stderr.write(f"  ERROR fetching body for {url}: {e}\n")

        items.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": TAGS,
            "excerpt": (excerpt or body)[:500],
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        })

        sys.stderr.write(
            f"  [{idx+1}/{len(url_list)}] {'OK' if pub_date else 'NO DATE'} — "
            f"{artist or '?'} : {album or title[:40]}"
            f"{' (' + pub_date + ')' if pub_date else ''}"
            f" (body: {len(body)} chars)\n"
        )

    if body_tab_id:
        close_tab(body_tab_id)

    # Sort by date descending (most recent first), then by title
    def sort_key(item):
        d = item.get("pub_date", "")
        return d if d else "0000-00-00"

    items.sort(key=sort_key, reverse=True)

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": today.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
        },
        "items": items,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"Total: {len(items)} reviews\n")


if __name__ == "__main__":
    main()
