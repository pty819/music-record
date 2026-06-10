#!/usr/bin/env python3
"""
scrape_point_of_departure.py — Scrape Point of Departure (PoD), the
improvised/creative music journal (https://pointofdeparture.org/), for the
current issue (PoD95, June 2026).

Strategy:
  - PoD has no RSS feed. The table-of-contents page (/Content.html) lists all
    article URLs for the current issue.
  - There are two layout families:
      1) Article / feature pages (PageOne, Hanes, Henkin, Ezz-thetics) —
         P0 is the title, P1 is the byline, P2+ is body text.
      2) Moment's Notice single-review page (PoD95MomentsNotice.html) —
         P0/P1 are headers, P2 is the <em>Artist<br><strong>Album</strong>
         <br>Label</em> header, P4+ is body, last body paragraph contains
         `<br><em>–ReviewerName</em>`.
      3) Multi-review aggregator pages (PoD95MoreMoments2.html) — chunks of
         [header <em>, body paragraphs], separated by <p>&nbsp;</p>.
      4) Book review page (PoD95Leroy.html, linked from PoD95BookCooks) —
         P0 = "The Book Cooks / Excerpt from", P1 = book title / author /
         publisher, body paragraphs separated by "***" markers.
  - The site is JS-rendered; every page fetch goes through Camoufox on
    localhost:9377. We reuse ONE tab across all navigations.

CLI:
  --days N              (default 1.5)  — hard cutoff window in days
  --ref-date YYYY-MM-DD (optional)    — override reference date (default: today UTC)
  --out-file PATH       (optional)    — also write JSON here

Output JSON shape:
  { "meta": {...}, "items": [...] }
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
SITE_BASE = "https://pointofdeparture.org"
LIST_URL = f"{SITE_BASE}/Content.html"

SITE_ID = "point_of_departure"
SOURCE = "Point of Departure"
TAGS_DEFAULT = "improvised music,creative music,jazz"
ISSUE = "PoD95"
ISSUE_DATE = "June2026"
PUB_DATE = "2026-06"  # issue month, no exact day available

USER_ID = "scraper_pod"
SESSION_KEY = "session_pod"

# Filter non-music releases (BLU-RAY / UHD / VOD / DVD tags in any text)
NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|BLU-RAY REVIEW|UHD|VOD|DVD)\)", re.I)

# Listing regex from spec.
# Content.html emits both /PoD95/PoD95X.html (absolute-ish) and PoD95/PoD95X.html
# (relative). Match either with a tolerant pattern.
ARTICLE_HREF_RE = re.compile(r"(?:^|/)PoD95/PoD95[A-Za-z0-9_-]+\.html$")

# Byline regex (em-dash prefix inside <em>...</em>)
BYLINE_RE = re.compile(r"<em>\s*[–\-]\s*([^<]+?)\s*</em>", re.I)
BYLINE_PLAIN_RE = re.compile(r"^[–\-]\s*(.+?)\s*$")

# Aggregator (multi-review) page filenames — cap at 2 listing pages per spec.
# MomentsNotice.html is itself a single-review page; MoreMoments2 is the first
# true multi-review aggregator page. We intentionally exclude MoreMoments3
# and MoreMoments4.
AGGREGATOR_PAGES = [
    "PoD95MomentsNotice.html",   # page 1 — single review
    "PoD95MoreMoments2.html",    # page 2 — multi-review aggregator
]


# ── Camoufox REST helpers ──────────────────────────────────────────────
def _api(method: str, path: str, body: dict | None = None, timeout: int = 90) -> dict:
    """Single JSON request to the Camoufox REST server."""
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {body_text}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


# ── JS expressions (run inside the browser) ────────────────────────────
# JS to enumerate article links from /Content.html
LISTING_JS = r"""
() => {
    const anchors = document.querySelectorAll('a[href]');
    const out = [];
    for (const a of anchors) {
        const href = a.getAttribute('href') || '';
        out.push({
            href: href,
            text: (a.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200)
        });
    }
    return out;
}
"""

# JS to extract a page's structured paragraph dump.
# Returns: { title, paragraphs: [{i, html, text, is_blank}], href }
PAGE_JS = r"""
() => {
    const ps = document.querySelectorAll('p');
    const out = [];
    for (let i = 0; i < ps.length; i++) {
        const t = (ps[i].innerText || '').replace(/\s+/g, ' ').trim();
        const h = (ps[i].innerHTML || '').trim();
        out.push({
            i: i,
            html: h,
            text: t,
            is_blank: t.length === 0,
            is_nbsp_only: /^(&nbsp;|\s|&amp;nbsp;)+$/i.test(h)
        });
    }
    return {
        title: document.title || '',
        url: location.href,
        paragraphs: out
    };
}
"""


# ── Parsing helpers ────────────────────────────────────────────────────
def normalize_href(href: str) -> str:
    """Return a fully-qualified PoD URL for a Content.html-relative href."""
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return f"{SITE_BASE}{href}"
    if href.startswith("PoD95"):
        return f"{SITE_BASE}/PoD95/{href}"
    return f"{SITE_BASE}/PoD95/{href}"


def parse_aggregator_page(paragraphs: list[dict], page_url: str) -> list[dict]:
    """
    Split a multi-review aggregator page into individual review chunks.

    The aggregator pages have:
        P0: page title (e.g. "Moment's Notice")
        P1: subtitle (e.g. "Reviews of Recent Media (continued)")
        then repeating blocks of:
            [<em>Artist<br><strong>Album</strong><br>Label</em>, body...]
        separated by <p>&nbsp;</p> separators.
        Pn-1: "> More Moment's Notice"
        Pn:   "> back to contents"

    Each chunk has:
        - First paragraph is the header <em>Artist<br><strong>Album</strong>...
        - Followed by 3-6 body paragraphs
        - Last body paragraph ends with `<br><em>–ReviewerName</em>`

    Returns a list of dicts:
        { artist, album, label, reviewer, body, raw_html }
    """
    chunks = []
    current = []

    for p in paragraphs:
        text = p["text"]
        html = p["html"]

        # Skip the page-level title + subtitle
        if p["i"] == 0 or p["i"] == 1:
            continue

        # Separator: <p>&nbsp;</p> with blank text — closes current chunk
        if p["is_blank"] and p["is_nbsp_only"]:
            if current:
                chunks.append(current)
                current = []
            continue

        # Navigation / footer paragraphs: blank, or "More Moment's Notice" / "back to"
        if not text:
            # Blank paragraph that's not &nbsp; — also a separator
            if current:
                chunks.append(current)
                current = []
            continue
        if text.startswith(">") and ("back to" in text.lower() or "more" in text.lower()):
            if current:
                chunks.append(current)
                current = []
            continue
        # Image-only paragraph (starts with <img)
        if html.lstrip().startswith("<img"):
            # Attach image info to current chunk's first body paragraph
            if current:
                current.append({"i": p["i"], "html": html, "text": text, "is_blank": False, "is_nbsp_only": False})
            continue

        current.append(p)

    # Flush trailing chunk
    if current:
        chunks.append(current)

    # Convert each chunk to a review dict
    reviews = []
    for chunk in chunks:
        if not chunk:
            continue
        header = chunk[0]
        body_paras = chunk[1:]

        # Extract artist/album/label from header HTML
        # Header pattern: <em>Artist<br><strong>Album</strong><br>Label/Catalog</em>
        h_html = header["html"]
        # Strong text = album
        m_album = re.search(r"<strong[^>]*>(.*?)</strong>", h_html, re.S | re.I)
        album = ""
        if m_album:
            album = re.sub(r"<[^>]+>", "", m_album.group(1)).strip()

        # All em content (artist + label)
        m_em = re.search(r"<em[^>]*>(.*?)</em>", h_html, re.S | re.I)
        if m_em:
            em_inner = m_em.group(1)
            # Split on <br>
            parts = re.split(r"<br\s*/?>", em_inner, flags=re.I)
            clean = []
            for pt in parts:
                t = re.sub(r"<[^>]+>", "", pt).strip()
                if t:
                    clean.append(t)
            # clean[0] = artist, clean[1] = album (from <strong>), clean[2] = label
            artist = clean[0] if len(clean) >= 1 else ""
            if not album and len(clean) >= 2:
                album = clean[1]
            label = clean[2] if len(clean) >= 3 else (clean[1] if len(clean) == 2 and not album else "")
        else:
            artist = header["text"].split("\n")[0].strip() if header["text"] else ""
            label = ""

        # Concatenate body paragraphs
        body_texts = []
        reviewer = ""
        for bp in body_paras:
            t = bp["text"]
            if not t:
                continue
            # Extract byline if present (last <em>–Name</em> in paragraph HTML)
            m_by = BYLINE_RE.search(bp["html"])
            if m_by:
                reviewer = m_by.group(1).strip()
                # Strip the byline marker from the rendered text
                t = re.sub(r"\s*[–\-]\s*[A-Z][\w .’'-]+\s*$", "", t).strip()
            body_texts.append(t)
        body = "\n\n".join(body_texts).strip()

        reviews.append({
            "artist": artist,
            "album": album,
            "label": label,
            "reviewer": reviewer,
            "body": body,
        })

    return reviews


def parse_single_review_page(paragraphs: list[dict], page_url: str, page_title: str) -> dict:
    """
    Parse a single-review page (MomentsNotice.html style).

    Layout:
        P0: <span><strong>"Moment's Notice"</strong></span>           (title)
        P1: <span><strong>Reviews of Recent Media</strong></span>    (subtitle)
        P2: <em>Artist<br><strong>Album</strong><br>Label</em>       (header)
        P3: blank
        P4..Pn-1: body paragraphs
        Pn: "> back to contents" or "> More..."
    """
    artist, album, label, reviewer = "", "", "", ""
    body_paras = []

    for p in paragraphs:
        text = p["text"]
        html = p["html"]

        # Skip the title and subtitle
        if p["i"] == 0 or p["i"] == 1:
            continue

        # Stop at navigation
        if text.startswith(">") and ("back to" in text.lower() or "more" in text.lower()):
            break

        # Header: <em>Artist<br><strong>Album</strong><br>Label</em>
        if not artist and "<em" in html.lower() and "<strong" in html.lower() and p["i"] <= 4:
            m_album = re.search(r"<strong[^>]*>(.*?)</strong>", html, re.S | re.I)
            if m_album:
                album = re.sub(r"<[^>]+>", "", m_album.group(1)).strip()
            m_em = re.search(r"<em[^>]*>(.*?)</em>", html, re.S | re.I)
            if m_em:
                em_inner = m_em.group(1)
                parts = re.split(r"<br\s*/?>", em_inner, flags=re.I)
                clean = []
                for pt in parts:
                    t = re.sub(r"<[^>]+>", "", pt).strip()
                    if t:
                        clean.append(t)
                artist = clean[0] if clean else ""
                if not album and len(clean) >= 2:
                    album = clean[1]
                label = clean[2] if len(clean) >= 3 else ""
            continue

        # Blank or image-only — skip
        if not text:
            continue
        if html.lstrip().startswith("<img"):
            continue

        # Body paragraph; check for byline
        m_by = BYLINE_RE.search(html)
        if m_by:
            reviewer = m_by.group(1).strip()
            text = re.sub(r"\s*[–\-]\s*[A-Z][\w .’'-]+\s*$", "", text).strip()
        if text:
            body_paras.append(text)

    body = "\n\n".join(body_paras).strip()
    return {
        "artist": artist,
        "album": album,
        "label": label,
        "reviewer": reviewer,
        "body": body,
    }


def parse_feature_page(paragraphs: list[dict], page_title: str) -> dict:
    """
    Parse a feature (column / interview) page: PageOne, Hanes, Henkin,
    Ezz-thetics.

    Layout:
        P0: page title (also <title>)
        P1: "by X" or "a column by\nX"
        P2: blank or subtitle
        P3..Pn-1: body
        Pn-1 / Pn: "© 2026 X" then "> back to contents"
    """
    body_paras = []
    reviewer = ""
    for p in paragraphs:
        text = p["text"]
        html = p["html"]

        # Skip the title
        if p["i"] == 0:
            continue

        # Skip navigation
        if text.startswith(">") and ("back to" in text.lower() or "more" in text.lower()):
            break

        # Skip blank
        if not text:
            continue

        # Detect byline ("by X" on P1 or P2, or "a column by\nX" with newline)
        if p["i"] in (1, 2) and re.match(r"^(a column by|by)\b", text, re.I):
            # Strip the leading "by" / "a column by"
            cleaned = re.sub(r"^(a column by|by)\s*", "", text, flags=re.I).strip()
            # Take the first name token
            reviewer = cleaned.split("\n")[0].strip()
            continue

        # Copyright line at end
        if "©" in text and re.match(r"^©\s*\d{4}", text):
            continue

        body_paras.append(text)

    body = "\n\n".join(body_paras).strip()
    return {
        "artist": "",
        "album": "",
        "label": "",
        "reviewer": reviewer,
        "body": body,
    }


def parse_book_review_page(paragraphs: list[dict], page_url: str, page_title: str) -> dict:
    """
    Parse a single book-review page (e.g. PoD95Leroy.html).

    Layout (observed):
        P0: "The Book Cooks\nExcerpt from"
        P1: "Book Title:\nSubtitle\nAuthor\n(Publisher; City)"
        P2: blank
        P3+: body sections separated by "***" markers
        Pn-2: "© 2026 Author"
        Pn-1: blank
        Pn:   "> Order Book Here"
        Pn+1: "> back to The Book Cooks"
    """
    artist, album, label, reviewer = "", "", "", ""
    body_paras = []

    # P1 holds the book header: lines are title, author, (publisher; city)
    if len(paragraphs) >= 2:
        h_text = paragraphs[1]["text"]
        lines = [ln.strip() for ln in h_text.split("\n") if ln.strip()]
        if lines:
            album = lines[0]  # book title becomes "album" field
            # The author line(s) — any line that doesn't end with a year and isn't parenthetical
            for ln in lines[1:]:
                if ln.startswith("(") and ln.endswith(")"):
                    label = ln.strip("()")
                elif not reviewer:
                    reviewer = ln

    for p in paragraphs:
        text = p["text"]
        html = p["html"]

        # Skip the cover header paragraphs
        if p["i"] in (0, 1):
            continue

        # Stop at navigation
        if text.startswith(">") and ("back to" in text.lower() or "order" in text.lower()):
            break

        # Skip "***" separators
        if text.strip() == "***":
            continue

        # Skip blank
        if not text:
            continue

        # Copyright line
        if "©" in text and re.match(r"^©\s*\d{4}", text):
            continue

        body_paras.append(text)

    body = "\n\n".join(body_paras).strip()
    return {
        "artist": artist,
        "album": album,
        "label": label,
        "reviewer": reviewer,
        "body": body,
    }


def is_aggregator_url(url: str) -> bool:
    """True if this URL points at one of the Moment's Notice multi-review pages."""
    return any(url.endswith(fn) for fn in AGGREGATOR_PAGES)


def is_book_review_url(url: str) -> bool:
    """Heuristic: per-book review pages are linked from PoD95BookCooks.html.
    In practice we only have one such URL (PoD95Leroy.html), so name-match."""
    return "BookCooks" in url or "Leroy" in url


def non_music(artist: str, album: str, body: str) -> bool:
    """Return True if any text field flags this as non-music (BLU-RAY/UHD/VOD/DVD)."""
    blob = f"{artist}\n{album}\n{body}"
    return bool(NON_MUSIC_RE.search(blob))


# ── Item builder ───────────────────────────────────────────────────────
def build_item(*, url: str, item_type: str, artist: str, album: str,
               label: str, reviewer: str, body: str) -> dict | None:
    """Assemble a standardized JSON item. Returns None if non-music."""
    if non_music(artist, album, body):
        sys.stderr.write(f"  SKIP (non-music): {artist} – {album}\n")
        return None

    excerpt = body[:500]
    return {
        "album": album,
        "artist": artist,
        "score": None,
        "url": url,
        "source": SOURCE,
        "pub_date": PUB_DATE,
        "tags": TAGS_DEFAULT,
        "excerpt": excerpt,
        "body": body,
        "site_id": SITE_ID,
        "crawl_status": "ok",
        "type": item_type,
        "label": label,
        "reviewer": reviewer,
    }


# ── Main ───────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Point of Departure (PoD)")
    parser.add_argument("--days", type=float, default=1.5,
                        help="Hard cutoff window in days (default 1.5 = 36h)")
    parser.add_argument("--ref-date", type=str, default=None,
                        help="Reference date YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--out-file", type=str, default=None,
                        help="Also write JSON output to this path")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    if args.ref_date:
        ref_date = datetime.strptime(args.ref_date, "%Y-%m-%d").date()
    else:
        ref_date = now.date()
    cutoff_date = ref_date - timedelta(days=args.days)
    cutoff_iso = cutoff_date.isoformat()

    sys.stderr.write(
        f"PoD scraper — Now: {now.isoformat()}, Ref: {ref_date.isoformat()}, "
        f"Cutoff: {cutoff_iso}, Days: {args.days}\n"
    )

    # ── Step 1: open a tab on the listing page ─────────────────────────
    tab_resp = _api("POST", "/tabs", {
        "userId": USER_ID,
        "sessionKey": SESSION_KEY,
        "url": LIST_URL,
    })
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        result = {"meta": {"total": 0, "scraped_at": now.isoformat(),
                            "cutoff_date": cutoff_iso, "site": SITE_ID,
                            "issue": ISSUE, "issue_date": ISSUE_DATE},
                  "items": []}
        _emit(result, args.out_file)
        sys.exit(1)

    all_items: list[dict] = []
    try:
        time.sleep(2)

        # ── Step 2: enumerate article URLs from the listing ────────────
        resp = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": LISTING_JS})
        anchors = resp.get("result") or []
        sys.stderr.write(f"Found {len(anchors)} anchors on listing page\n")

        # Build article URL list
        article_urls: list[str] = []
        seen: set[str] = set()
        for a in anchors:
            href = a.get("href", "")
            if not href or not ARTICLE_HREF_RE.search(href):
                continue
            # Skip BookCooks (the index of book reviews) — handled via Leroy
            if href.endswith("BookCooks.html"):
                continue
            # Skip the aggregator pages from auto-list — handled separately
            if any(href.endswith(fn) for fn in AGGREGATOR_PAGES):
                continue
            full = normalize_href(href)
            if full in seen:
                continue
            seen.add(full)
            article_urls.append(full)

        # Always include the book review (Leroy) and the 2 aggregator pages
        article_urls.append(f"{SITE_BASE}/PoD95/PoD95Leroy.html")
        for fn in AGGREGATOR_PAGES:
            article_urls.append(f"{SITE_BASE}/PoD95/{fn}")
        # De-duplicate while preserving order
        deduped: list[str] = []
        seen2: set[str] = set()
        for u in article_urls:
            if u not in seen2:
                seen2.add(u)
                deduped.append(u)
        article_urls = deduped

        sys.stderr.write(f"Article URLs to fetch ({len(article_urls)}):\n")
        for u in article_urls:
            sys.stderr.write(f"  - {u}\n")

        # ── Step 3: navigate to each article and parse ──────────────────
        for i, url in enumerate(article_urls):
            sys.stderr.write(f"\n[{i + 1}/{len(article_urls)}] {url}\n")
            try:
                _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                time.sleep(2.5)
                resp = _api("POST", f"/tabs/{tab_id}/evaluate",
                            {"expression": PAGE_JS})
            except Exception as e:
                sys.stderr.write(f"  ERROR fetching {url}: {e}\n")
                blocked = build_item(
                    url=url, item_type="feature",
                    artist="", album="", label="", reviewer="",
                    body="",
                )
                if blocked is not None:
                    blocked["crawl_status"] = "blocked"
                    all_items.append(blocked)
                continue

            data = resp.get("result") or {}
            title = data.get("title", "")
            paragraphs = data.get("paragraphs") or []
            sys.stderr.write(f"  title={title!r} paragraphs={len(paragraphs)}\n")

            # Branch on page type
            if is_aggregator_url(url):
                # Multi-review aggregator OR single-review Moment's Notice page
                # (MomentsNotice.html is structurally a single review — detect
                # by counting how many <em>Artist<br><strong>Album</strong>...
                # headers we find; if only 1, treat as single review).
                reviews = parse_aggregator_page(paragraphs, url)
                # If the aggregator yielded just one review, it's MomentsNotice
                if len(reviews) == 1:
                    r = reviews[0]
                    item = build_item(
                        url=url, item_type="review",
                        artist=r["artist"], album=r["album"],
                        label=r["label"], reviewer=r["reviewer"],
                        body=r["body"],
                    )
                    if item:
                        all_items.append(item)
                else:
                    for r in reviews:
                        item = build_item(
                            url=url, item_type="review",
                            artist=r["artist"], album=r["album"],
                            label=r["label"], reviewer=r["reviewer"],
                            body=r["body"],
                        )
                        if item:
                            all_items.append(item)
            elif is_book_review_url(url):
                parsed = parse_book_review_page(paragraphs, url, title)
                item = build_item(
                    url=url, item_type="review",
                    artist=parsed["artist"], album=parsed["album"],
                    label=parsed["label"], reviewer=parsed["reviewer"],
                    body=parsed["body"],
                )
                if item:
                    all_items.append(item)
            else:
                # Feature / column / interview page
                parsed = parse_feature_page(paragraphs, title)
                item = build_item(
                    url=url, item_type="feature",
                    artist=parsed["artist"], album=parsed["album"],
                    label=parsed["label"], reviewer=parsed["reviewer"],
                    body=parsed["body"],
                )
                if item:
                    all_items.append(item)

        # ── Step 4: emit JSON ──────────────────────────────────────────
        result = {
            "meta": {
                "total": len(all_items),
                "scraped_at": now.isoformat(),
                "cutoff_date": f"{cutoff_iso}T00:00:00+00:00",
                "site": SITE_ID,
                "issue": ISSUE,
                "issue_date": ISSUE_DATE,
            },
            "items": all_items,
        }
        _emit(result, args.out_file)
        sys.stderr.write(f"\nTotal: {len(all_items)} items\n")

    finally:
        try:
            _api("DELETE", f"/tabs/{tab_id}")
            sys.stderr.write(f"Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"WARNING: failed to close tab: {e}\n")


def _emit(result: dict, out_file: str | None) -> None:
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    print(payload)
    if out_file:
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.write("\n")
        sys.stderr.write(f"Wrote {out_file}\n")


if __name__ == "__main__":
    main()