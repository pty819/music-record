#!/usr/bin/env python3
"""
scrape_truth_and_lies_music.py — Camoufox-based scraper for Truth & Lies Music.

Site: https://www.truthandliesmusic.com/ (Squarespace)
No RSS feed available — use Camoufox to scrape listing + article pages.

Strategy:
  1. Navigate to /magazine listing page
  2. Extract all article cards (title, URL, date)
  3. Paginate page 2 (page 2 is all 2025 — typically beyond 36h window, but check)
  4. Filter by 36h cutoff
  5. Visit each article for full body text, tags, type classification
  6. Output standardized JSON
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
BASE_URL = "https://www.truthandliesmusic.com"
LIST_URL = f"{BASE_URL}/magazine"

SITE_ID = "truth_and_lies_music"
SOURCE = "Truth & Lies Music"
TAGS_DEFAULT = ""
USER_ID = "scraper_tnl"
SESSION_KEY = "session_tnl"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
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


def parse_date(text: str) -> str | None:
    """Parse 'June 3, 2026' into ISO date."""
    text = (text or "").strip()
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
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


def classify_post(title: str) -> str:
    """Determine if a post is 'review', 'feature', or 'tracklist'."""
    t = title.lower()
    if " - a review" in t or " - review" in t:
        return "review"
    if " - single premiere!" in t or " - premiere!" in t:
        return "feature"
    if "a conversation between" in t or "interview" in t:
        return "feature"
    if "tracklist" in t or "track list" in t:
        return "tracklist"
    if "review" in t:
        return "review"
    return "feature"


def split_artist_album(title: str):
    """Parse title like 'ARTIST 'ALBUM' (LABEL) - A REVIEW' into artist, album."""
    # Strip the type suffix: " - A REVIEW", " - SINGLE PREMIERE!", " - PREMIERE!"
    cleaned = re.sub(r"\s*-\s*(A\s+)?(REVIEW|SINGLE\s+)?PREMIERE!?\s*$", "", title, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*-\s*A\s+REVIEW\s*$", "", cleaned, flags=re.IGNORECASE).strip()

    # Try to extract "ARTIST 'ALBUM' (LABEL)" or "ARTIST \u201cALBUM\u201d (LABEL)"
    # Pattern: starts with artist name, then quoted album
    m = re.match(
        r"^(.+?)\s+[`\u2018\u2019\u201c\u201d](.+)[`\u2019\u201d\u201c]\s*(\([^)]*\))?(?:\s*-\s*.*)?$",
        cleaned,
    )
    if m:
        artist = m.group(1).strip()
        album = m.group(2).strip()
        return artist, album

    # Try splitting on ' - ' or ' \u2013 ' or ' \u2014 '
    for sep in [" - ", " \u2013 ", " \u2014 "]:
        if sep in cleaned:
            parts = cleaned.split(sep, 1)
            artist = parts[0].strip()
            album = parts[1].strip()
            return artist, album

    return "", cleaned


# JS to extract listing cards from the /magazine page
EXTRACT_LISTING_JS = r"""
() => {
    const articles = document.querySelectorAll('article');
    const results = [];
    for (const art of articles) {
        const a = art.querySelector('a[href*="/magazine/"]');
        if (!a) continue;
        const href = a.getAttribute('href') || '';
        let title = (a.innerText || '').trim();
        if (!title) {
            const fullText = (art.innerText || '').trim();
            title = fullText.split('\n')[0].trim();
        }
        const artText = art.innerText || '';
        const dateMatch = artText.match(
            /(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}/
        );
        const dateText = dateMatch ? dateMatch[0] : '';
        if (title) {
            results.push({ title, href, date_text: dateText });
        }
    }
    return results;
}
"""

# JS to extract body, tags, and date from an article page
EXTRACT_ARTICLE_JS = r"""
() => {
    const article = document.querySelector('article');
    const bodyText = article ? (article.innerText || '').trim() : (document.body.innerText || '').trim();

    const tagMatch = bodyText.match(/Tags\s+([A-Za-z0-9_,\s-]+?)(?:\n|0\s*Likes|$)/i);
    let tags = '';
    if (tagMatch) {
        tags = tagMatch[1].trim();
    }

    const dateMatch = bodyText.match(
        /(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}/
    );
    const dateText = dateMatch ? dateMatch[0] : '';
    const pageTitle = document.title || '';

    let cleanBody = bodyText;
    // Remove trailing "In CATEGORIES" line
    cleanBody = cleanBody.replace(/\nIn\s+[A-Z,\s]+\s*$/, '');
    // Remove "Tags ..." line
    cleanBody = cleanBody.replace(/\nTags\s+[A-Za-z0-9_,\s-]+/, '');
    // Remove "0 Likes" and "Share"
    cleanBody = cleanBody.replace(/\n0\s*Likes(\s*Share)?/g, '');
    // Remove "← Previous Next →" patterns
    cleanBody = cleanBody.replace(/←[^\n]*\n?/g, '');
    cleanBody = cleanBody.replace(/→[^\n]*\n?/g, '');
    // Remove comment section
    cleanBody = cleanBody.replace(/\nComments\s*\(\d+\)[\s\S]*$/, '');
    // Collapse whitespace
    cleanBody = cleanBody.replace(/\n{3,}/g, '\n\n').trim();

    return {
        body: cleanBody,
        page_title: pageTitle,
        date_text: dateText,
        tags: tags,
    };
}
"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape Truth & Lies Music")
    parser.add_argument("--pages", type=int, default=2, help="Max listing pages to scan")
    parser.add_argument("--days", type=float, default=1.5, help="Max age in days")
    parser.add_argument("--date", type=str, default=None, help="Explicit cutoff date YYYY-MM-DD")
    parser.add_argument("--no-article-pages", action="store_true", help="Skip article body extraction")
    args = parser.parse_args()
    pages = min(args.pages, 2)

    now = datetime.now(timezone.utc)
    if args.date:
        cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        cutoff_date = (now - timedelta(days=args.days)).date()
    cutoff_iso = cutoff_date.isoformat()

    sys.stderr.write(
        f"T&L scraper — Now: {now.isoformat()}, Cutoff: {cutoff_iso}, Pages: {pages}\n"
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

        # ── Step 1: Collect cards from listing pages ────────────────────
        all_cards = []
        seen_urls = set()

        for page_num in range(1, pages + 1):
            sys.stderr.write(f"\n=== Page {page_num} ===\n")
            if page_num == 1:
                pass
            else:
                page_url = f"{LIST_URL}?page={page_num}"
                _api("POST", f"/tabs/{tab_id}/navigate", {"url": page_url})
                time.sleep(2)

            resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                "expression": EXTRACT_LISTING_JS,
            })
            cards = resp.get("result") or []
            sys.stderr.write(f"Found {len(cards)} cards on page {page_num}\n")
            for c in cards:
                href = c.get("href", "")
                url = href if href.startswith("http") else f"{BASE_URL}{href}"
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_cards.append(c)
                    sys.stderr.write(f"  [{len(all_cards)}] {c.get('title', '')[:60]} \u2014 date: {c.get('date_text', '')}\n")

        sys.stderr.write(f"\nTotal unique cards: {len(all_cards)}\n")

        # ── Step 2: Date filter + normalize ─────────────────────────────
        kept = []
        for c in all_cards:
            href = c.get("href", "")
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            title = (c.get("title") or "").strip()
            date_text = c.get("date_text") or ""

            # Non-music filter
            if NON_MUSIC_RE.search(title):
                sys.stderr.write(f"  SKIP (non-music): {title[:60]}\n")
                continue

            # Parse date and check cutoff
            pub_date = parse_date(date_text) or ""
            if not pub_date:
                sys.stderr.write(f"  SKIP (no date): {title[:60]}\n")
                continue
            try:
                item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
            except ValueError:
                continue
            if item_date < cutoff_date:
                sys.stderr.write(f"  SKIP (out of window {pub_date}): {title[:60]}\n")
                continue

            # Classify type
            post_type = classify_post(title)

            # Parse artist/album
            artist, album = split_artist_album(title)

            kept.append({
                "album": album if album else title,
                "artist": artist,
                "score": None,
                "url": url,
                "source": SOURCE,
                "pub_date": pub_date,
                "tags": "",
                "excerpt": "",
                "body": "",
                "site_id": SITE_ID,
                "crawl_status": "pending",
                "type": post_type,
            })

        sys.stderr.write(f"Items in 36h window: {len(kept)}\n")

        # ── Step 3: Visit each article for full body ─────────────────────
        if not args.no_article_pages and kept:
            sys.stderr.write(f"\n=== Visiting {len(kept)} articles for body text ===\n")
            for i, item in enumerate(kept):
                url = item["url"]
                sys.stderr.write(f"  [{i+1}/{len(kept)}] {item['artist'] or '?'} : {item['album'][:50]}\n")
                try:
                    _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                    time.sleep(1.5)
                    resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
                        "expression": EXTRACT_ARTICLE_JS,
                    })
                    detail = resp.get("result") or {}
                    body = (detail.get("body") or "").strip()
                    tags_raw = (detail.get("tags") or "").strip()

                    if body:
                        item["body"] = body
                        item["excerpt"] = body[:500].replace("\n", " ")
                        item["crawl_status"] = "success"
                    else:
                        item["crawl_status"] = "empty"

                    if tags_raw:
                        item["tags"] = tags_raw

                    sys.stderr.write(f"    body: {len(item['body'])} chars, tags: {item['tags'][:50]}\n")
                except Exception as e:
                    sys.stderr.write(f"    ERROR: {e}\n")
                    item["crawl_status"] = "partial"
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
        output_path = "/home/liyifan/music-record/2026/06/2026-06-05/truth_and_lies_music_reviews.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"\nTotal: {len(all_items)} items \u2014 written to {output_path}\n")

    finally:
        try:
            _api("DELETE", f"/tabs/{tab_id}")
            sys.stderr.write(f"Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"WARNING: Failed to close tab: {e}\n")


if __name__ == "__main__":
    main()
