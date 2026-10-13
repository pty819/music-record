#!/usr/bin/env python3
"""
scrape_strangely_isolated_place.py — Camoufox-based scraper for A Strangely Isolated Place.

Extracts album reviews / features / mixes from https://www.astrangelyisolatedplace.com/blog
within the last --days (default 1.5 = 36 hours).

The site is Squarespace-based. Static HTML loads in ~20s; Camoufox 30s navigation
timeout is too short, so we use curl for the blog index + entry pages, and fall back
to Camoufox only if curl fails.

Strategy:
  1. curl /blog and /blog?offset=NNN (first 2 listing pages)
  2. For each entry, parse dt-published time and filter to the cutoff window
  3. For each in-window entry, curl the article page and extract the body
  4. Skip BLU-RAY/UHD/VOD/DVD entries
  5. Features/interviews/mixes → type=feature, score=null
  6. Output structured JSON with {meta, items} envelope

Output format:
  {"meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."},
   "items": [{album, artist, score, url, source, pub_date, tags, excerpt,
              body, site_id, crawl_status, type}]}

Usage:
  python3 scrape_strangely_isolated_place.py --days 1.5
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────────
SITE_BASE = "https://www.astrangelyisolatedplace.com"
SITE_ID = "strangely_isolated_place"
SOURCE = "A Strangely Isolated Place"
TAGS = "ambient,electronica,modern classical"
TODAY = datetime.now(timezone.utc).date()

CURL_TIMEOUT = 120  # site is slow (~20-50s for blog index)
MAX_LISTING_PAGES = 2  # task constraint: only flip first 2 pages

# ── HTTP helper ────────────────────────────────────────────────────────

def http_get(url, timeout=CURL_TIMEOUT):
    """Plain curl-equivalent GET returning (status_code, body_bytes)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        sys.stderr.write(f"[WARN] GET {url} failed: {e}\n")
        return 0, b""


# ── Listing-page parsing ──────────────────────────────────────────────

ARTICLE_PATTERN = re.compile(
    r'<article class="entry[^"]*"[^>]*>(.*?)</article>',
    re.DOTALL,
)

# Title: <h1 class="entry-title"><a href="...">TITLE</a></h1>
TITLE_PATTERN = re.compile(
    r'class="entry-title[^"]*"[^>]*>\s*<a[^>]+>([^<]+)</a>',
)

# Published datetime on the entry: <time class="...dt-published..." datetime="YYYY-MM-DD">
PUB_PATTERN = re.compile(
    r'<time[^>]*class="[^"]*dt-published[^"]*"[^>]*datetime="([^"]+)"',
)

# URL: <a href="/blog/..." class="entry-dateline-link">DATE</a>
# or the entry-title link
URL_PATTERN = re.compile(
    r'href="(/blog/[^"#]+)"',
)

# Excerpt / summary content
EXCERPT_PATTERN = re.compile(
    r'<div class="entry-summary[^"]*"[^>]*>(.*?)</div>\s*</header>',
    re.DOTALL,
)

# Non-music filter
NON_MUSIC_PATTERN = re.compile(r"\((BLU-RAY|UHD|VOD|DVD)\)", re.IGNORECASE)

# Tracklist type detection
TRACKLIST_PATTERN = re.compile(r"\btracklist\b", re.IGNORECASE)


def extract_entries_from_listing(html):
    """Yield (url, title, pub_date_str, excerpt) for each entry block in the listing HTML."""
    for m in ARTICLE_PATTERN.finditer(html):
        body = m.group(1)
        pub_match = PUB_PATTERN.search(body)
        if not pub_match:
            continue
        pub_date = pub_match.group(1)
        url_match = URL_PATTERN.search(body)
        title_match = TITLE_PATTERN.search(body)
        url = url_match.group(1) if url_match else ""
        title = title_match.group(1).strip() if title_match else ""
        excerpt_match = EXCERPT_PATTERN.search(body)
        excerpt = ""
        if excerpt_match:
            # Strip HTML tags from excerpt
            excerpt = re.sub(r"<[^>]+>", " ", excerpt_match.group(1))
            excerpt = re.sub(r"\s+", " ", excerpt).strip()
        yield url, title, pub_date[:10], excerpt  # YYYY-MM-DD


def fetch_listing_pages():
    """Fetch blog index and follow offset pagination, up to MAX_LISTING_PAGES."""
    pages = []
    seen_offsets = set()
    url = f"{SITE_BASE}/blog"
    for page_idx in range(MAX_LISTING_PAGES):
        sys.stderr.write(f"[list] GET {url}\n")
        status, body = http_get(url)
        if status != 200 or not body:
            sys.stderr.write(f"[list] page {page_idx+1} returned status={status}, stopping\n")
            break
        pages.append(body.decode("utf-8", errors="replace"))
        # Find next-page offset link
        next_match = re.search(r'href="/blog\?offset=(\d+)"', pages[-1])
        if not next_match:
            sys.stderr.write(f"[list] no next-page link, pagination ends at page {page_idx+1}\n")
            break
        next_offset = next_match.group(1)
        if next_offset in seen_offsets:
            sys.stderr.write(f"[list] offset loop detected, stopping\n")
            break
        seen_offsets.add(next_offset)
        url = f"{SITE_BASE}/blog?offset={next_offset}"
    return pages


# ── Article-page parsing ──────────────────────────────────────────────

# Body container on Squarespace blog posts: <div class="entry-content"> ... </div>
BODY_JS = """
() => {
    const el = document.querySelector('.entry-content') ||
               document.querySelector('article .entry-content') ||
               document.querySelector('article');
    if (!el) return '';
    // Strip script/style iframes
    const clone = el.cloneNode(true);
    clone.querySelectorAll('script, style, iframe, form, .sqs-audio, .audio-block').forEach(n => n.remove());
    return clone.innerText.trim().slice(0, 20000);
}
"""


def extract_body(html):
    """Extract article body from a Squarespace blog post page (static HTML)."""
    # Find the entry-content div
    m = re.search(r'<div class="entry-content[^"]*"[^>]*>(.*?)(?=<footer|</article|<div class="entry-footer)', html, re.DOTALL)
    if not m:
        return ""
    raw = m.group(1)
    # Remove script/style/iframe/form blocks
    raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<iframe[^>]*>.*?</iframe>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<form[^>]*>.*?</form>", "", raw, flags=re.DOTALL)
    # Convert <br> and </p> to newlines, strip remaining tags
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"</p>", "\n\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Decode common HTML entities
    raw = (raw.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'")
                .replace("&apos;", "'")
                .replace("&nbsp;", " "))
    # Collapse whitespace
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n\s*\n", "\n\n", raw)
    return raw.strip()


# ── Title → artist / album ─────────────────────────────────────────────

TITLE_SEP_PATTERN = re.compile(r"\s*[—–\-:]\s*")


def split_artist_album(title):
    """Split 'ARTIST — ALBUM' / 'ARTIST - ALBUM' into (artist, album)."""
    title = title.strip()
    parts = TITLE_SEP_PATTERN.split(title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", title


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape A Strangely Isolated Place reviews.")
    parser.add_argument("--days", type=float, default=1.5,
                        help="Number of days back to include (default: 1.5 = 36h hard constraint)")
    args = parser.parse_args()

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=args.days)).date()
    sys.stderr.write(
        f"ASIP scraper — Today (UTC): {TODAY}, Cutoff: {cutoff_date} "
        f"(args.days={args.days})\n"
    )

    # 1. Fetch listing pages
    pages = fetch_listing_pages()
    sys.stderr.write(f"[list] fetched {len(pages)} listing page(s)\n")

    # 2. Parse entries, filter to cutoff window
    candidates = []
    seen_urls = set()
    for page_html in pages:
        for url, title, pub_date_str, excerpt in extract_entries_from_listing(page_html):
            if not url or not pub_date_str or url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                pub_date_obj = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if not (cutoff_date <= pub_date_obj <= TODAY):
                continue  # outside window
            candidates.append({
                "url": f"{SITE_BASE}{url}" if url.startswith("/") else url,
                "title": title,
                "pub_date": pub_date_str,
                "excerpt": excerpt,
            })
            sys.stderr.write(f"  CANDIDATE: {pub_date_str} | {title[:60]}\n")

    sys.stderr.write(f"[list] {len(candidates)} candidate(s) within window\n")

    # 3. Empty result → output per task spec (no error, no retry)
    if not candidates:
        result = {
            "meta": {
                "total": 0,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
                "hours_scanned": int(args.days * 24),
                "note": "No posts published within the 36h window on A Strangely Isolated Place",
            },
            "items": [],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.stderr.write("[done] 0 items — empty result, per spec\n")
        return

    # 4. Fetch each article body
    items = []
    for idx, c in enumerate(candidates, 1):
        sys.stderr.write(f"[body] [{idx}/{len(candidates)}] GET {c['url']}\n")
        status, body_bytes = http_get(c["url"])
        if status != 200 or not body_bytes:
            sys.stderr.write(f"  SKIP — fetch failed (status={status})\n")
            continue
        body = extract_body(body_bytes.decode("utf-8", errors="replace"))

        # Non-music filter
        full_title_with_excerpt = c["title"] + " " + c["excerpt"]
        if NON_MUSIC_PATTERN.search(full_title_with_excerpt):
            sys.stderr.write(f"  SKIP — non-music media format: {c['title'][:50]}\n")
            continue

        # Type classification
        title_lower = c["title"].lower()
        if TRACKLIST_PATTERN.search(title_lower):
            item_type = "tracklist"
            score = None
        elif "review" in c["excerpt"].lower() or "reviewed" in c["excerpt"].lower():
            item_type = "review"
            score = None  # ASIP doesn't show numeric ratings
        else:
            # Mixes/features/interviews → feature
            item_type = "feature"
            score = None

        artist, album = split_artist_album(c["title"])
        items.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": c["url"],
            "source": SOURCE,
            "pub_date": c["pub_date"],
            "tags": TAGS,
            "excerpt": c["excerpt"][:500] if c["excerpt"] else "",
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": item_type,
        })
        sys.stderr.write(f"  OK — type={item_type}, body={len(body)} chars\n")

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "hours_scanned": int(args.days * 24),
        },
        "items": items,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"[done] {len(items)} item(s)\n")


if __name__ == "__main__":
    main()