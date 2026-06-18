#!/usr/bin/env python3
"""
scrape_wild_city.py — Camoufox-based scraper for Wild City.

Wild City (thewildcity.com) uses a custom CMS (Mamoka Boilerplate). All content
is server-rendered. The homepage/features page has a sidebar feed of all recent
items, each tagged with data-date="DD/MM/YYYY". Items fall into three URL shapes:
  /news/NNNN-slug     — short news / announcement (e.g. label signing, release)
  /features/NNNN-slug — long-form review or feature; Review: prefix in title
                       means album review
  /podcasts/NNNN-slug — Wild City podcast episode (not music content)

Per the kanban task spec, the 36h window is the hard cutoff. Items with type:
  "Review:" prefix   → type: "review"
  anything else      → type: "feature" (news, announcements, interviews)

Strategy:
  1. Open ONE tab on /features (or homepage) — the sidebar feed is identical.
  2. Extract all `a.box[data-date]` items with their data-date, href, title.
  3. Filter by cutoff date (parsed DD/MM/YYYY).
  4. Skip podcast items (/podcasts/) — not music.
  5. Skip non-music items: titles containing (BLU-RAY)/(UHD)/(VOD)/(DVD) tokens.
  6. For each remaining item, navigate to its URL and fetch full body.
  7. Parse artist/album from title for "Review:" items only.
  8. Output JSON envelope {meta, items} to stdout.

This avoids the broken approach of the previous script: looking only for
"Review:" prefix missed all the actual recent content, which lives in /news/
and uses feature/article format rather than album-review format.

Usage:
  python3 scrape_wild_city.py [--days 1.5] [--max-items 20]
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "")
# /features carries the full sidebar feed; /home does too
TARGET_URL = "https://www.thewildcity.com/features"

SITE_ID = "wild_city"
SOURCE = "Wild City"
TAGS = "indie,electronic,india"
USER_ID = "scraper_wild_city"
SESSION_KEY = "session_wc"

# Non-music tokens to skip
NON_MUSIC_RE = re.compile(r"\((BLU-RAY|UHD|VOD|DVD)\)", re.IGNORECASE)

# ── Helpers ────────────────────────────────────────────────────────────


def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Make a JSON API call to the Camoufox REST server."""
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
    )
    if data:
        req.add_header("Content-Type", "application/json")
    if CAMOFOX_API_KEY:
        req.add_header("Authorization", f"Bearer {CAMOFOX_API_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


def close_tab(tab_id: str) -> None:
    """Safely close a Camoufox tab."""
    if tab_id:
        try:
            _api("DELETE", f"/tabs/{tab_id}?userId={USER_ID}")
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
        sys.stderr.write(f"  Tab {tab_id} created, waiting for page load...\n")
        time.sleep(8)
        return tab_id
    except Exception as e:
        sys.stderr.write(f"  ERROR creating tab: {e}\n")
        return None


def evaluate_js(tab_id: str, expression: str):
    """Evaluate JS expression in a Camoufox tab. Returns the result value."""
    try:
        resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "userId": USER_ID, "expression": expression})
        return resp.get("result")
    except Exception as e:
        sys.stderr.write(f"  ERROR evaluating JS: {e}\n")
        return None


def navigate(tab_id: str, url: str) -> bool:
    """Navigate an existing tab to a new URL.

    POST /tabs/{id}/navigate reuses the tab; POST /tabs always CREATES a
    new tab (server ignores the tabId field). Critical for body fetch.
    """
    try:
        _api("POST", f"/tabs/{tab_id}/navigate", {"userId": USER_ID, "url": url})
        sys.stderr.write(f"  Navigated to {url[:80]}...\n")
        time.sleep(6)
        return True
    except Exception as e:
        sys.stderr.write(f"  ERROR navigating tab: {e}\n")
        return False


def fetch_body(tab_id: str) -> str:
    """Fetch full body text from the current page via JS evaluation."""
    # NOTE: must be a plain expression, not a function definition.
    # page.evaluate(string) evals as JS expr — arrow function would be returned as object, not called.
    js = "document.querySelector('article')?.innerText?.slice(0, 12000) || document.body?.innerText?.slice(0, 12000) || ''"
    try:
        result = evaluate_js(tab_id, js)
        if result is None:
            return ""
        return str(result).strip()
    except Exception as e:
        sys.stderr.write(f"  ERROR fetching body: {e}\n")
        return ""


def parse_date_dd_mm_yyyy(text: str) -> str:
    """Parse 'DD/MM/YYYY' format date. Returns ISO string or ''."""
    text = (text or "").strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text)
    if not m:
        return ""
    try:
        dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return dt.date().isoformat()
    except ValueError:
        return ""


# ── Title parsing for "Review:" prefixed items ────────────────────────

TITLE_SEP_PATTERN = re.compile(r"\s*[—–-]\s*")


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

    For non-Review: items, we return (artist='', album=title) — the entire
    title stays as the "album" so downstream consumers can still see what
    the article is about.
    """
    title = (title or "").strip()
    if title.lower().startswith("review:"):
        title = title[7:].strip()
    elif title.lower().startswith("review — "):
        title = title[9:].strip()
    title = title.strip()

    if not title.lower().startswith("review:") and "review:" not in title.lower()[:20]:
        # Not a review — keep whole title, no artist parsing
        return "", title

    # Find album in quotes — handle apostrophes inside by using lookbehind/
    # lookahead to ensure ' is a quote delimiter, not an apostrophe
    album = ""
    artist = ""
    quote_pairs = [
        (r"\u2018((?:[^\u2018\u2019]|\u2019(?=\w))+?)\u2019(?=\s|,|\.|!|\?|$)", "single-smart"),
        (r"\u201c((?:[^\u201c\u201d]|\u201d(?=\w))+?)\u201d(?=\s|,|\.|!|\?|$)", "double-smart"),
        (r"(?:^|\s|,)\x27((?:[^\x27]|\x27(?=\w))+?)\x27(?=\s|,|\.|!|\?|$)", "single-ascii"),
        (r"\x22((?:[^\x22]|\x22(?=\w))+?)\x22", "double-ascii"),
    ]

    album_start = -1
    album_end = -1

    for pattern, kind in quote_pairs:
        for m in re.finditer(pattern, title):
            candidate = m.group(1).strip()
            if len(candidate) < 2:
                continue
            if len(candidate) > len(album):
                album = candidate
                album_start = m.start()
                album_end = m.end()

    if not album:
        # Try possessive pattern: "ARTIST's SOMETHING Bridges..."
        poss_match = re.search(
            r"^(.+?)'s\s+(.+?)(?:\s+(?:bridges|marks|sees|is|has|makes|showcases|infuses|returns))",
            title)
        if poss_match:
            artist = poss_match.group(1).strip()
            album_candidate = poss_match.group(2).strip()
            if album_candidate.lower() not in ("sophomore", "debut", "new", "latest"):
                album = album_candidate
            else:
                sub_match = re.search(
                    r"(?:sophomore\s+)?(?:album|debut|ep|mixtape|single|lp)\s+['\u2018\u2019](.+?)['\u2018\u2019]",
                    title[poss_match.end():])
                if sub_match:
                    album = sub_match.group(1).strip()
                else:
                    album = album_candidate
            return artist.strip(), album.strip()
        # No quotes, no possessive — use whole title
        return "", title

    # ── Extract artist ──
    before = title[:album_start].strip().rstrip(",").strip()
    after = title[album_end:].strip().lstrip(",").strip()

    if not before or len(before) < 3:
        by_match = re.search(r"\bby\s+(.+?)$", after, re.IGNORECASE)
        if by_match:
            artist = by_match.group(1).strip()
        elif re.match(r"on\s+", before, re.IGNORECASE) or after.startswith(","):
            after_clean = after.lstrip(",").strip()
            artist = after_clean.split()[0] if after_clean else ""
        else:
            artist = ""
    elif before.lower().startswith("on "):
        if not before[3:].strip() or before[3:].strip() == "on":
            after_clean = after.lstrip(",").strip()
            artist = re.split(
                r"\s+(?:keeps|finds|bridges|marks|sees|doesn|does|presents|is|has|makes|returns|turns)",
                after_clean, maxsplit=1, flags=re.IGNORECASE)[0].strip().rstrip(",")
        else:
            artist = before[3:].strip()
    else:
        poss_found = False
        for poss_char in ["\u2019", "'", "\u2018"]:
            poss_pattern = rf"{re.escape(poss_char)}s(?:\s|$)"
            if re.search(poss_pattern, before):
                artist = re.sub(poss_pattern, " ", before).strip()
                poss_found = True
                break
        if not poss_found:
            artist = re.split(
                r"\s+(?:finds|doesn|does|bridges|marks|presents|sees|"
                r"keeps|returns|turns|steps|infuses|makes|aims|flips|"
                r"mixes|introduces|comes|launches)\b",
                before, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            artist = re.sub(
                r"\s+(?:on|with|for|the|their|his|her|a|an|to)\s*$",
                "", artist, flags=re.IGNORECASE).strip()

    artist = artist.strip().strip(",").strip("'\"")
    album = album.strip().strip(",").strip("'\u2018\u2019\u201c\u201d")
    artist = re.sub(
        r"\s+(?:sophomore\s+)?(?:album|debut|ep|mixtape|single|lp|new|latest)\s*$",
        "", artist, flags=re.IGNORECASE).strip()

    noisy_artists = {"finds", "doesn", "does", "bridges", "marks", "presents",
                     "sees", "keeps", "returns", "turns", "steps", "infuses",
                     "makes", "aims", "flips", "mixes", "introduces", "comes",
                     "launches", "on"}
    if artist.lower() in noisy_artists:
        artist = ""

    return artist.strip(), album.strip()


# ── JS extraction expressions ──────────────────────────────────────────

# Extract all sidebar feed items with their data-date, href, title
EXTRACT_FEED_JS = """
const items = [];
const seen = new Set();
const els = document.querySelectorAll('a.box[data-date]');
for (const el of els) {
    const href = el.getAttribute('href') || '';
    if (!href || seen.has(href)) continue;
    seen.add(href);
    const date = el.getAttribute('data-date') || '';
    // Title is the first line of innerText (sometimes a tag comes first)
    const text = (el.innerText || '').trim();
    const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
    let title = lines[0] || '';
    // Sometimes there's a tag pill like "Review" or "Podcast" before the title
    if (lines.length > 1 && /^(review|podcast|feature|tracklist|interview|news)$/i.test(lines[0])) {
        title = lines[1] || title;
    }
    items.push({
        url: href.startsWith('http') ? href : 'https://www.thewildcity.com' + href,
        date: date,
        title: title,
    });
}
items;
"""


# ── Main ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Scrape Wild City items")
    parser.add_argument(
        "--days", type=float, default=1.5,
        help="Max age in days for articles (default: 1.5 — kanban-mandated 36h window)"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Explicit cutoff date (YYYY-MM-DD). Overrides --days."
    )
    parser.add_argument(
        "--max-items", type=int, default=20,
        help="Max number of product pages to fetch body text (default: 20). "
             "Capped to avoid iteration budget exhaustion in kanban."
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

    # Phase 1: Collect feed items with data-date
    sys.stderr.write("Phase 1: Collecting feed from /features...\n")
    tab_id = create_tab(TARGET_URL)
    if not tab_id:
        result = {"meta": {"total": 0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)

    try:
        feed_raw = evaluate_js(tab_id, EXTRACT_FEED_JS) or []
        sys.stderr.write(f"  Found {len(feed_raw)} feed items\n")
    finally:
        close_tab(tab_id)

    # Phase 2: Filter by cutoff date, skip podcasts, skip non-music
    sys.stderr.write(f"Phase 2: Filtering by cutoff {cutoff_date} and skipping non-music...\n")
    candidates = []
    skipped_old = 0
    skipped_podcast = 0
    skipped_non_music = 0
    for item in feed_raw:
        url = item.get("url", "")
        date_str = item.get("date", "")
        title = item.get("title", "")

        if not url or not date_str or not title:
            continue

        # Skip podcast items
        if "/podcasts/" in url.lower() or url.lower().endswith("podcasts"):
            skipped_podcast += 1
            continue

        # Skip non-music tokens
        if NON_MUSIC_RE.search(title):
            skipped_non_music += 1
            continue

        pub_date = parse_date_dd_mm_yyyy(date_str)
        if not pub_date:
            continue

        try:
            item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
        except ValueError:
            continue

        if item_date < cutoff_date:
            skipped_old += 1
            continue

        candidates.append({"url": url, "date": date_str, "pub_date": pub_date, "title": title})

    sys.stderr.write(
        f"  After filter: {len(candidates)} candidates "
        f"(skipped: {skipped_old} old, {skipped_podcast} podcast, {skipped_non_music} non-music)\n"
    )

    # Phase 3: Fetch full body for each candidate
    max_items = min(args.max_items, 20)
    sys.stderr.write(f"\nPhase 3: Fetching full body for up to {max_items} items...\n")

    items = []
    url_list = candidates[:max_items]
    for idx, c in enumerate(url_list):
        url = c["url"]
        title = c["title"]
        pub_date = c["pub_date"]

        # Type / score: "Review:" prefix → review, else feature
        is_review = title.lower().startswith("review:")
        item_type = "review" if is_review else "feature"
        score = None  # Wild City doesn't publish star ratings

        # Artist / album: only parse for reviews
        if is_review:
            artist, album = extract_artist_album(title)
        else:
            artist, album = "", title

        # Fetch body — create a fresh tab per URL instead of navigating
        # (POST /tabs/{id}/navigate is unreliable — crashes the server)
        body = ""
        body_tab = create_tab(url)
        if body_tab:
            time.sleep(5)  # extra wait for page render
            body = fetch_body(body_tab)
            close_tab(body_tab)

        excerpt = (body[:500] if body else title)

        items.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": TAGS,
            "excerpt": excerpt,
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success" if body else "empty_body",
            "type": item_type,
        })

        sys.stderr.write(
            f"  [{idx+1}/{len(url_list)}] {item_type.upper():7s} — "
            f"{artist or '?'} : {(album or title)[:60]}"
            f" ({pub_date}, body: {len(body)} chars)\n"
        )

    # Sort by date descending (most recent first)
    items.sort(key=lambda it: it.get("pub_date", "") or "0000-00-00", reverse=True)

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": today.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "hours_scanned": int(args.days * 24),
        },
        "items": items,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"\nTotal: {len(items)} items\n")


if __name__ == "__main__":
    main()
