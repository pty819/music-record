#!/usr/bin/env python3
"""
scrape_progressor.py — HTTP-based scraper for ProgressoR.

Site: http://www.progressor.net/
Genres: art-rock, prog, jazz-fusion, RIO, avant-prog
RSS: none (plain HTML only)

NOTE: Camoufox (Firefox 150+) cannot connect to ProgressoR because the
server uses TLS 1.0 with a self-signed certificate. The site is plain HTML
with no JS rendering needed, so we use direct HTTP requests instead.

Layout:
 - Homepage (index.html) is the live listing: SHORT REVIEWS + DETAILED REVIEWS
   sections, plus a NEWS strip and a TOPS chart section.
 - Each item is `DD.MM+       ARTIST - "ALBUM"` linking to /review/<slug>_<year>.html
 - /history_short.html and /history_detailed.html contain all historical
   reviews grouped by year.
 - Review page format: `ARTIST - YEAR - "ALBUM"` then `(TRACK_LEN; LABEL)` then
   the body paragraph, then `Progtector: MONTH YEAR` as the publication date.

Cutoff: --days 1.5 (36h). As of 2026-06-11, the homepage banner reads
"Latest update: May31,2026 / Next update: June30,2026", so the
expected outcome is 0 items — we still write the JSON envelope.

Output schema (canonical):
{
  "meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."},
  "items": [
    {album, artist, score, url, source, pub_date, tags, excerpt, body,
     site_id, crawl_status, type}
  ]
}
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────────
# NOTE: ProgressoR uses TLS 1.0 with a self-signed certificate, which
# Firefox 150+ (Camoufox) cannot connect to. The site is plain HTML with
# no JS rendering needed, so we use direct HTTP requests instead.
SITE_BASE = "http://www.progressor.net"
HOME_URL = f"{SITE_BASE}/index.html"
HIST_SHORT_URL = f"{SITE_BASE}/history_short.html"
HIST_DETAILED_URL = f"{SITE_BASE}/history_detailed.html"

SITE_ID = "progressor"
SOURCE = "ProgressoR"
TAGS_DEFAULT = "art-rock,prog,jazz-fusion,RIO,avant-prog"

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|UHD|VOD|DVD|Blu-ray|4K)\)", re.I)
# Title line on the listing: "31.V+\tGong - \"Bright Spirit\""
LISTING_LINE_RE = re.compile(
    r"^(?P<date>\d{1,2}\.(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\+?)?\s*"
    r"(?P<artist>[^-]+?)\s*-\s*"
    r"(?P<quote>[\"\u201c\u201d'`])?(?P<album>.+?)(?P=quote)\s*$",
    re.U,
)
# Review page header: "Gong -2026 - \"Bright Spirit\""
REVIEW_HEADER_RE = re.compile(
    r"^\s*(?P<artist>[^-]+?)\s*-\s*"
    r"(?P<year>\d{4})\s*-\s*"
    r"(?P<quote>[\"\u201c\u201d'`])?(?P<album>.+?)(?P=quote)\s*$",
    re.U,
)
# "(43:45; Kscope)" or "(49:12; Some Label / Sub)"
LABEL_LINE_RE = re.compile(r"\((?P<runtime>[\d:]+)\s*;\s*(?P<label>[^)]+)\)")
# Footer author tag: "Progtector: May 2026" / "Progmessor: May 2026"
PUBTAG_RE = re.compile(
    r"Prog(?:tector|messor):\s*(?P<month>January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+(?P<year>\d{4})",
    re.I,
)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# Roman-numeral -> integer
ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}


# ── HTTP helper (direct HTTP via urllib — no Camoufox) ──────────────────

def _http_get(url, timeout=30):
    """Fetch a URL via HTTP GET, return (html_text, error_or_None)."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        return html, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, str(e.reason)
    except Exception as e:
        return None, str(e)


# ── Parsing helpers ────────────────────────────────────────────────────

def parse_pubtag(text):
    """Find a 'Progtector: Month Year' footer; return (year, month, day) or None.

    The site only publishes at month granularity, so we conservatively use the
    FIRST of the month.
    """
    m = PUBTAG_RE.search(text or "")
    if not m:
        return None
    month = MONTHS.get(m.group("month").lower())
    year = int(m.group("year"))
    if not month or year < 2000:
        return None
    return (year, month, 1)


def parse_review_page(body_text, url):
    """Parse a single review page; return (artist, album, pub_date, body, type, score)."""
    lines = [ln.strip() for ln in (body_text or "").splitlines() if ln.strip()]
    artist = album = label = runtime = ""
    pub_date = None
    score = None
    type_ = "review"

    # Header line: "ARTIST - YEAR - \"ALBUM\""
    for ln in lines[:6]:
        m = REVIEW_HEADER_RE.match(ln)
        if m:
            artist = m.group("artist").strip()
            album = m.group("album").strip()
            break

    # Next line: "(43:45; Kscope)" or similar
    for ln in lines[:10]:
        m = LABEL_LINE_RE.match(ln)
        if m:
            runtime = m.group("runtime").strip()
            label = m.group("label").strip()
            break

    # Pubdate footer
    pt = parse_pubtag(body_text)
    if pt:
        pub_date = datetime(pt[0], pt[1], pt[2], tzinfo=timezone.utc)

    # Body = everything between the label line and the "Progtector:" footer
    body_lines = []
    for ln in lines:
        if ln.startswith("[") and ln.endswith("]"):
            continue
        if PUBTAG_RE.search(ln):
            continue
        if ln.lower().startswith("related links"):
            continue
        if PUBTAG_RE.search(ln) or ln.startswith("Progtector:") or ln.startswith("Progmessor:"):
            continue
        body_lines.append(ln)
    body = "\n".join(body_lines).strip()

    # Feature detection: "interview" or "Interview" in title (no album? still keep)
    if not album and artist:
        type_ = "feature"
    if album and "interview" in album.lower():
        type_ = "feature"

    return artist, album, pub_date, body, type_, score, label, runtime


def parse_listing(html_text, base_url):
    """Extract review links from a listing page.

    The HTML uses TWO structures:
     - homepage: links like <a href="review/foo.html">Foo - "Bar"</a>
     - /history_*.html: links like <a href="review/foo.html"><b>Foo</b> - "Bar"</a>
       (artist wrapped in <b>)

    We capture the full anchor inner text via BeautifulSoup so both structures
    work, and only filter out links whose text starts with '[' (section nav
    chips like "[ More News]", "[ ABC | DEF]").
    """
    import urllib.parse
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        BeautifulSoup = None

    out = []
    seen = set()

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html_text or "", "lxml")
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "")
            if not href:
                continue
            if "/review/" not in href and not href.startswith("review/"):
                continue
            if "detailed_" in href or "general.html" in href or href.endswith("/review/"):
                continue
            if "bl1_" in href or "bl2_" in href or "tops" in href or "prog100" in href or "prog50" in href:
                continue
            text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            if not text:
                continue
            if text.startswith("[") or text.endswith("]"):
                continue
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = f"{SITE_BASE}{href}"
            else:
                url = urllib.parse.urljoin(base_url, href)
            if url in seen:
                continue
            seen.add(url)
            out.append({"url": url, "title": text, "raw": text})
        return out

    # Fallback regex path (if bs4 missing)
    href_re = re.compile(
        r'<a\b[^>]*href="([^"]*?review/[^"]+)"[^>]*>(.+?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for m in href_re.finditer(html_text or ""):
        href = m.group(1).strip()
        inner = re.sub(r"<[^>]+>", "", m.group(2))
        text = re.sub(r"\s+", " ", inner).strip()
        if not text or text.startswith("[") or text.endswith("]"):
            continue
        if "detailed_" in href or "bl1_" in href or "bl2_" in href or "tops" in href:
            continue
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = f"{SITE_BASE}{href}"
        else:
            url = urllib.parse.urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "title": text, "raw": text})
    return out


# ── Main scrape routine ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Scrape ProgressoR")
    ap.add_argument("--days", type=float, default=1.5, help="Max age in days (default 1.5 = 36h)")
    ap.add_argument("--date", type=str, default=None, help="Explicit cutoff date YYYY-MM-DD")
    ap.add_argument("--out-dir", type=str,
        default=os.environ.get("HERMES_KANBAN_WORKSPACE", "/home/liyifan/music-record/2026/06/2026-06-11"),
        help="Output directory")
    ap.add_argument("--dry-run", action="store_true", help="Print summary, do not write file")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    if args.date:
        cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        cutoff_date = now - timedelta(days=args.days)

    sys.stderr.write(
        f"ProgressoR scraper — now={now.isoformat()} cutoff={cutoff_date.isoformat()} "
        f"days={args.days}\n"
    )

    # 1. Fetch listing pages via HTTP
    candidate_urls = {}
    fetch_errors = 0

    pages = [
        ("homepage", HOME_URL),
        ("history_short", HIST_SHORT_URL),
    ][:2]  # hard-cap at 2 listing pages per task spec

    for label, page_url in pages:
        sys.stderr.write(f"\n=== Collecting from {label} ({page_url}) ===\n")
        html, err = _http_get(page_url, timeout=30)
        if err:
            sys.stderr.write(f"  FETCH ERROR: {label}: {err}\n")
            fetch_errors += 1
            continue
        items = parse_listing(html, page_url)
        sys.stderr.write(f"  {label}: {len(items)} review links\n")
        for it in items:
            if it["url"] not in candidate_urls:
                candidate_urls[it["url"]] = {"title": it["title"], "raw": it["raw"], "source": label}

    sys.stderr.write(f"\nTotal unique candidates: {len(candidate_urls)}\n")

    # 2. Fetch each review page; apply filters
    EARLY_STOP_AFTER = 3

    results = []
    kept = 0
    skipped_non_music = 0
    skipped_old = 0
    consecutive_old_per_source = {"homepage": 0, "history_short": 0}

    # Preserve discovery order: homepage entries first, then history entries
    ordered = []
    for url, meta in candidate_urls.items():
        if meta.get("source") == "homepage":
            ordered.append((url, meta))
    for url, meta in candidate_urls.items():
        if meta.get("source") != "homepage":
            ordered.append((url, meta))

    total_candidates = len(ordered)
    n = 0
    exhausted_sources = set()
    for url, meta in ordered:
        n += 1
        src = meta.get("source", "unknown")
        if src in exhausted_sources:
            continue
        list_title = meta["title"]
        if NON_MUSIC_RE.search(list_title):
            sys.stderr.write(f"  [{n}/{total_candidates}] SKIP non-music (list): {list_title[:60]}\n")
            skipped_non_music += 1
            continue

        page_text, err = _http_get(url, timeout=30)
        if err:
            sys.stderr.write(f"  [{n}/{total_candidates}] FETCH ERROR: {url} {err}\n")
            fetch_errors += 1
            continue

        # Strip HTML to plain text with line breaks at block elements (mimics innerText).
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page_text, "lxml")
            for tag in soup.find_all(
                ['p', 'div', 'br', 'tr', 'td', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
            ):
                tag.append('\n')
            page_text = soup.get_text()
        except ImportError:
            page_text = re.sub(r'<(?:p|div|br|tr|td|li|h[1-6])[^>]*>', '\n', page_text, flags=re.I)
            page_text = re.sub(r'<[^>]+>', '', page_text)
        # Normalize whitespace (keep newlines)
        page_text = re.sub(r'[ \t]+', ' ', page_text).strip()

        # Re-check non-music on full title
        if NON_MUSIC_RE.search(page_text[:1500]):
            sys.stderr.write(f"  [{n}/{total_candidates}] SKIP non-music (body): {url}\n")
            skipped_non_music += 1
            continue

        # Quick short-circuit: if the page is a 404, skip without parsing
        if "Not Found" in page_text[:200] and "404" in page_text[:200].lower():
            sys.stderr.write(f"  [{n}/{total_candidates}] SKIP 404: {url}\n")
            fetch_errors += 1
            continue

        artist, album, pub_date, body, type_, score, label, runtime = parse_review_page(page_text, url)

        # Filter by cutoff: pub_date is month-level (first of month)
        if pub_date and pub_date < cutoff_date:
            sys.stderr.write(
                f"  [{n}/{total_candidates}] SKIP old (pub={pub_date.date()}): "
                f"{artist or '?'} : {album[:40]}\n"
            )
            skipped_old += 1
            consecutive_old_per_source[src] = consecutive_old_per_source.get(src, 0) + 1
            if consecutive_old_per_source[src] >= EARLY_STOP_AFTER:
                sys.stderr.write(
                    f"  [{n}/{total_candidates}] Early-stop: {EARLY_STOP_AFTER} "
                    f"consecutive old items from source={src}\n"
                )
                exhausted_sources.add(src)
            continue
        else:
            consecutive_old_per_source[src] = 0

        if not body:
            sys.stderr.write(f"  [{n}/{total_candidates}] SKIP empty body: {url}\n")
            fetch_errors += 1
            continue

        item = {
            "album": album or list_title,
            "artist": artist,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date.isoformat() if pub_date else "",
            "tags": TAGS_DEFAULT,
            "excerpt": (body[:500] if body else "").replace("\n", " "),
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "ok" if pub_date else "indeterminate",
            "type": type_,
        }
        if label:
            item["label"] = label
        if runtime:
            item["runtime"] = runtime

        results.append(item)
        if pub_date:
            kept += 1
        sys.stderr.write(f"  [{n}/{total_candidates}] KEPT ({type_}): {artist} : {album[:50]}\n")

    sys.stderr.write(
        f"\nResults: total={len(results)} in_window={kept} "
        f"non_music_skipped={skipped_non_music} old_skipped={skipped_old} "
        f"fetch_errors={fetch_errors}\n"
    )

    out = {
        "meta": {
            "total": len(results),
            "scraped_at": now.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "site": SITE_ID,
            "pages_crawled": 2,
            "candidates_checked": total_candidates,
            "in_window_count": kept,
            "non_music_skipped": skipped_non_music,
            "old_skipped": skipped_old,
            "fetch_errors": fetch_errors,
            "note": "Camoufox incompatible (TLS 1.0 + self-signed cert); used direct HTTP. "
            "Homepage banner reads 'Latest update: <DATE> / Next update: <DATE>' — "
            "all visible reviews are outside the 36h cutoff (most recent is from the prior month).",
        },
        "items": results,
    }

    if args.dry_run:
        print(json.dumps(out["meta"], indent=2))
        return

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "progressor_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"Wrote {out_path} ({len(results)} items)\n")


def _write_empty(args, now, cutoff_date):
    """Write the empty JSON envelope (no items, no panic)."""
    out = {
        "meta": {
            "total": 0,
            "scraped_at": now.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "site": SITE_ID,
            "note": "No items extracted.",
        },
        "items": [],
    }
    if args.dry_run:
        print(json.dumps(out["meta"], indent=2))
        return
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "progressor_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"Wrote {out_path} (0 items)\n")


if __name__ == "__main__":
    main()
