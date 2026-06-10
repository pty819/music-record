#!/usr/bin/env python3
"""
scrape_roots_world.py — Scrape RootsWorld (https://rootsworld.com/rw/) for album
reviews / features / podcast entries.

Strategy:
- Home page (/) is the listing — all current items are on a single page, no
  pagination. The task constraint "只翻前 2 页" is satisfied by capping at 1
  (there's no page 2 to flip to).
- Each <article class="review-card"> block has a thumb link + read-more link.
- Fetch every article page; parse div.review-header (when present) or fall
  back to page <title> + first text lines for artist/album/label/reviewer.
- Body: prefer div.review-body, else plain text after "Review by".
- Type:
  - "feature"  — feature/interview/editorial (no album; or has "Interview")
  - "tracklist" — podcast program (mixcloud iframe, no album review link)
  - "review"   — standard album review
- Non-music (BLU-RAY/UHD/VOD/DVD) is filtered.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString

SITE_ID = "roots_world"
SOURCE = "RootsWorld"
BASE = "https://rootsworld.com"
LIST_URL = f"{BASE}/rw/"

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|BLU-RAY REVIEW|UHD|VOD|DVD)\)", re.I)
REVIEWER_LINE_RE = re.compile(
    r"^(?:Reviewed\s+by|Review\s+by|By|Interview\s+and\s+review\s+by|"
    r"Recordings\s+and\s+Commentary\s+by|Commentary\s+by)\s+(.+)$",
    re.I,
)
PHOTO_LINE_RE = re.compile(r"^Photos?:", re.I)


def fetch(url: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["curl", "-sL", "-A", "Mozilla/5.0", "-m", str(timeout), url],
            capture_output=True, timeout=timeout + 5,
        )
        if result.returncode != 0:
            sys.stderr.write(f"curl error {result.returncode} for {url}\n")
            return ""
        return result.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        sys.stderr.write(f"fetch exception for {url}: {e}\n")
        return ""


def normalize_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return f"{BASE}{href}"
    if href.startswith("http"):
        return href
    return urljoin(LIST_URL, href)


def is_podcast_card(art) -> bool:
    """Detect a podcast / mixcloud tracklist entry (no review read-more link)."""
    has_mixcloud = bool(art.find("iframe", src=re.compile(r"mixcloud\.com", re.I)))
    has_review_link = bool(art.find("a", class_="read-more", href=re.compile(r"reviews/|interview/")))
    return has_mixcloud and not has_review_link


def parse_listing(html: str):
    """Return a list of dicts describing each article. Podcast cards are kept
    inline (no extra fetch — we use the home-page article body directly)."""
    soup = BeautifulSoup(html, "lxml")
    articles = soup.find_all("article", class_="review-card")
    out = []
    for art in articles:
        more = art.find("a", class_="read-more", href=True)
        is_podcast = is_podcast_card(art)
        href = ""
        list_title = ""
        if more:
            href = more.get("href", "")
            list_title = more.get_text(" ", strip=True)
        if not list_title:
            b = art.find("b")
            if b:
                list_title = b.get_text(" ", strip=True)
        if is_podcast:
            # For podcasts we point at the home page itself (with a unique
            # fragment per listing) and embed the raw article HTML for body
            # extraction later. Avoid following the external racethesky.com
            # thumb link.
            pod_idx = sum(1 for x in out if x.get("is_podcast"))
            url = f"{LIST_URL}#podcast-{pod_idx + 1}"
        else:
            url = normalize_url(href) if href else ""
        if not url:
            continue
        slug = url.rsplit("/", 1)[-1]
        out.append({
            "url": url,
            "slug": slug,
            "list_title": list_title,
            "is_podcast": is_podcast_card(art),
            "is_interview": "/interview/" in url,
            "raw_html": str(art),
        })
    return out


def _parse_header_p(hdr_p) -> str:
    """Get text of a header <p> skipping any nested links/breaks that add noise."""
    # Some p's have nested <br> and <a> + trailing "instruments" appended. Just
    # get the full text — should be one logical line.
    return re.sub(r"\s+", " ", hdr_p.get_text(" ", strip=True)).strip()


def extract_from_header_block(art_html: str) -> dict:
    """Parse an article that has <div class='review-header'> with structured fields."""
    soup = BeautifulSoup(art_html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    artist = album = label = reviewer = ""
    hdr = soup.find("div", class_="review-header")
    if hdr:
        # Walk through the <p> children; the first non-empty p (skipping img)
        # is the artist line, then album, then label, then reviewer.
        p_lines = []
        for child in hdr.children:
            if getattr(child, "name", None) is None:
                continue
            if child.name == "img":
                continue
            if child.name in ("p", "div", "span", "i", "b"):
                t = _parse_header_p(child)
                if t:
                    p_lines.append(t)
        # Identify reviewer line and Photo line
        reviewer_line = None
        photo_line = None
        for ln in p_lines:
            if REVIEWER_LINE_RE.match(ln):
                reviewer_line = ln
            elif PHOTO_LINE_RE.match(ln):
                photo_line = ln
        if reviewer_line:
            m = REVIEWER_LINE_RE.match(reviewer_line)
            if m:
                reviewer = m.group(1).strip()
        # Remaining lines (in order) = artist, album, label (may be 1, 2, or 3)
        field_lines = [
            ln for ln in p_lines
            if not REVIEWER_LINE_RE.match(ln) and not PHOTO_LINE_RE.match(ln)
        ]
        if len(field_lines) >= 1:
            artist = field_lines[0]
        if len(field_lines) >= 2:
            album = field_lines[1]
        if len(field_lines) >= 3:
            label = field_lines[2]

    body_text = ""
    body_div = soup.find("div", class_="review-body")
    if body_div:
        body_text = body_div.get_text("\n", strip=True)
    else:
        # fall back to entire <body> text
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = soup.find("body").get_text("\n", strip=True) if soup.find("body") else ""

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "label": label,
        "reviewer": reviewer,
        "body": body_text.strip(),
    }


def extract_plain_article(art_html: str) -> dict:
    """Article without review-header — first lines are Artist\\nAlbum\\nLabel\\nReview by X."""
    soup = BeautifulSoup(art_html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    body_text = soup.find("body").get_text("\n", strip=True) if soup.find("body") else ""
    # Trim boilerplate
    body_text = re.split(
        r"Search\s+RootsWorld|Subscribe\s+and\s+Support|Find\s+\w+\s+online",
        body_text, maxsplit=1
    )[0].strip()

    lines = [ln.strip() for ln in body_text.splitlines() if ln.strip()]
    reviewer = ""
    for ln in lines[:6]:
        m = REVIEWER_LINE_RE.match(ln)
        if m:
            reviewer = m.group(1).strip()
            break

    # Identify first 3 field lines, skipping Photo / Reviewer / bandcamp / "<a href" lines
    def is_field_line(ln: str) -> bool:
        if REVIEWER_LINE_RE.match(ln):
            return False
        if PHOTO_LINE_RE.match(ln):
            return False
        if ln.startswith("http") or ln.startswith("<a "):
            return False
        return True

    field_lines = []
    for ln in lines:
        if not is_field_line(ln):
            continue
        field_lines.append(ln)
        if len(field_lines) >= 3:
            break
    artist = field_lines[0] if len(field_lines) >= 1 else ""
    album = field_lines[1] if len(field_lines) >= 2 else ""
    label = field_lines[2] if len(field_lines) >= 3 else ""

    # Body without header
    body_clean = body_text
    # Drop everything up to and including the reviewer line
    if reviewer:
        m = re.search(
            r"(?:Review(?:ed)?\s+by|Review\s+by|By|Interview\s+and\s+review\s+by|"
            r"Recordings\s+and\s+Commentary\s+by|Commentary\s+by)\s+[^\n<]+",
            body_text, re.I,
        )
        if m:
            body_clean = body_text[m.end():].lstrip("\n ").lstrip()
    else:
        # No reviewer line; drop first 3 lines
        body_clean = "\n".join(lines[3:])

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "label": label,
        "reviewer": reviewer,
        "body": body_clean.strip(),
    }


def parse_article(art_html: str) -> dict:
    soup = BeautifulSoup(art_html, "lxml")
    if soup.find("div", class_="review-header"):
        return extract_from_header_block(art_html)
    return extract_plain_article(art_html)


def detect_type(parsed: dict, list_info: dict, body_text: str) -> str:
    if list_info["is_podcast"]:
        return "tracklist"
    if list_info["is_interview"]:
        return "feature"
    # No album but has artist → could be feature
    if not parsed["album"]:
        if "interview" in body_text[:400].lower() or "in his own words" in body_text[:400].lower():
            return "feature"
        if "recordings and commentary" in parsed.get("title", "").lower():
            return "feature"
        # If header is "Recordings and Commentary by X" pattern
        if re.search(r"^(Recordings?\s+and\s+Commentary|Commentary)\s+by", parsed.get("artist", ""), re.I):
            return "feature"
    return "review"


def _is_soundbites_special(parsed: dict) -> bool:
    """Sound Bites is a multi-review compilation page — give it a clean title."""
    return "sound bite" in parsed["title"].lower() or parsed.get("slug_marker", False)


def scrape(ref_date, max_pages: int = 1):
    cutoff = ref_date - timedelta(hours=36)
    sys.stderr.write(f"RootsWorld — ref={ref_date}, cutoff={cutoff.isoformat()}\n")

    list_html = fetch(LIST_URL)
    if not list_html:
        return {"meta": _meta(0, cutoff, listed=0), "items": []}

    listed = parse_listing(list_html)
    sys.stderr.write(f"Listing: {len(listed)} articles\n")

    items = []
    seen = set()
    for n, li in enumerate(listed, 1):
        if n > max_pages * 30:
            break
        url = li["url"]
        if url in seen:
            continue
        seen.add(url)

        # Filter non-music by listing title
        if NON_MUSIC_RE.search(li["list_title"]):
            sys.stderr.write(f"  skip (non-music): {url}\n")
            continue

        if li["is_podcast"]:
            # Use the home-page article HTML directly; no extra fetch
            parsed = parse_article(li["raw_html"])
            # Title comes from the listing
            title = li["list_title"]
            # Body is whatever prose is in the article (excluding the iframe)
            soup = BeautifulSoup(li["raw_html"], "lxml")
            text_parts = []
            for p in soup.find_all("p"):
                t = p.get_text(" ", strip=True)
                if t:
                    text_parts.append(t)
            body = "\n".join(text_parts)
            iframe_src = ""
            ifr = soup.find("iframe", src=True)
            if ifr:
                iframe_src = ifr["src"]
            parsed["title"] = title
            parsed["album"] = title
            parsed["artist"] = "RootsWorld Radio"
            parsed["body"] = body
        else:
            art_html = fetch(url)
            if not art_html:
                sys.stderr.write(f"  fetch failed: {url}\n")
                continue
            parsed = parse_article(art_html)
            body = parsed.get("body", "") or ""
            title = parsed.get("title", "") or ""

            # Filter non-music by full text
            if NON_MUSIC_RE.search(body + " " + title):
                sys.stderr.write(f"  skip (non-music body): {url}\n")
                continue

        # Special case: the Sound Bites page is a multi-review compilation
        if "soundbites" in li["slug"].lower() or "sound bites" in (title or "").lower():
            item_type = "tracklist"
            album = "Sound Bites: Songs and short reviews from around the world"
            artist = "RootsWorld"
            body_out = parsed.get("body", "")
        else:
            body = parsed.get("body", "") or ""
            title = parsed.get("title", "") or ""
            item_type = detect_type(parsed, li, body + " " + title)
            album = parsed["album"] or ""
            artist = parsed["artist"] or ""
            if not album and not artist:
                album = title
            body_out = body

        # Trim body: drop footer "Find ... online" / "Search RootsWorld" / etc.
        body_out = re.split(
            r"Search\s+RootsWorld|Subscribe\s+and\s+Support|Find\s+\w[\w\s]+\s+online\.?$",
            body_out, maxsplit=1
        )[0].strip()
        # Drop duplicate "Review by X" at the top
        body_out = re.sub(
            r"^(?:Review(?:ed)?\s+by|By|Commentary\s+by|Recordings\s+and\s+Commentary\s+by)\s+[^\n]+\n+",
            "", body_out, flags=re.I,
        ).strip()

        item = {
            "album": album,
            "artist": artist,
            "score": None,
            "url": url,
            "source": SOURCE,
            "pub_date": "",  # RootsWorld doesn't publish dates on the site
            "tags": "world music",
            "excerpt": body_out[:500] if body_out else "",
            "body": body_out,
            "site_id": SITE_ID,
            "crawl_status": "ok",
            "type": item_type,
        }
        if parsed.get("label"):
            item["label"] = parsed["label"]
        if parsed.get("reviewer"):
            item["reviewer"] = parsed["reviewer"]
        items.append(item)
        time.sleep(0.3)

    return {
        "meta": _meta(len(items), cutoff, listed=len(listed)),
        "items": items,
    }


def _meta(total, cutoff, listed=0):
    return {
        "total": total,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "cutoff_date": cutoff.isoformat(),
        "site": SITE_ID,
        "pages_crawled": 1,
        "articles_listed": listed,
        "note": "RootsWorld has no published dates on articles; all home-page -26 articles included. Body sourced from per-article page (div.review-body or first 3 text lines fallback).",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ref-date", help="Reference date YYYY-MM-DD (default: today UTC)")
    p.add_argument("--max-pages", type=int, default=1, help="Cap on listing pages (default 1)")
    args = p.parse_args()

    ref_date = (
        datetime.strptime(args.ref_date, "%Y-%m-%d").date()
        if args.ref_date
        else datetime.now(timezone.utc).date()
    )
    result = scrape(ref_date, args.max_pages)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"Done: {result['meta']['total']} items (cutoff={result['meta']['cutoff_date']})\n")


if __name__ == "__main__":
    main()
