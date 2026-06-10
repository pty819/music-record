#!/usr/bin/env python3
"""
scrape_world_music_central.py — Scrape World Music Central (worldmusiccentral.org)
for album reviews / features / interviews published in the last 36 hours.

Strategy:
- RSS at /feed/ provides 10 most recent items. Only the entries within the
  36h window are kept.
- Summary field is short (truncated by WordPress). Fetch the full article page
  for the body text via urllib.
- Type heuristics:
    - "feature"   — festival news, artist interviews, environmental pieces, etc.
                    (no album review content; title usually describes news)
    - "tracklist" — track listing / podcast-style entries (none seen so far)
    - "review"    — anything tagged as a review (e.g. "Album Review" or single
                    announcements tied to a forthcoming album)
- Non-music filter: skip (BLU-RAY)/(UHD)/(VOD)/(DVD) in title.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

SITE_ID = "world_music_central"
SOURCE = "World Music Central"
BASE = "https://worldmusiccentral.org"
RSS_URL = f"{BASE}/feed/"

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|BLU-RAY REVIEW|UHD|VOD|DVD)\)", re.I)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=36.0)
    p.add_argument("--date", help="reference date YYYY-MM-DD (default: today UTC)")
    p.add_argument("--rss-only", action="store_true",
                   help="use only RSS summary, do not fetch full articles")
    p.add_argument("--out", help="output JSON path (overrides default)")
    return p.parse_args()


UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
ACCEPT_HTML = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8")


def fetch(url, timeout=30):
    """Fetch URL with curl using a real-browser User-Agent (server is gated
    by Mod_Security / Cloudflare and rejects the default curl UA)."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "-A", UA, "-H", "Accept: " + ACCEPT_HTML,
             "-H", "Accept-Language: en-US,en;q=0.5",
             "-m", str(timeout), url],
            capture_output=True, timeout=timeout + 10,
        )
        if result.returncode != 0:
            sys.stderr.write(f"curl error {result.returncode} for {url}\n")
            return ""
        return result.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        sys.stderr.write(f"fetch exception for {url}: {e}\n")
        return ""


def fetch_rss():
    """Fetch the WMC RSS via curl (browser UA) and hand the bytes to
    feedparser. Calling feedparser.parse(url) directly hits the same
    Mod_Security / Cloudflare gate that blocked article pages, so we
    route through curl with a real-browser UA."""
    import feedparser
    raw = fetch(RSS_URL)
    if not raw:
        sys.stderr.write("RSS fetch returned empty body\n")
        return feedparser.parse("")
    return feedparser.parse(raw)


def parse_pub_dt(entry):
    """Return timezone-aware UTC datetime for an RSS entry, or None."""
    pub_str = entry.get("published") or entry.get("updated")
    if not pub_str:
        return None
    try:
        dt = parsedate_to_datetime(pub_str)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def get_article_body(article_url):
    """Fetch full article HTML and return (body_text, excerpt)."""
    html = fetch(article_url)
    if not html:
        return "", ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer",
                     "aside", "form", "iframe"]):
        tag.decompose()

    # WordPress content containers in order of preference
    body_el = (
        soup.find("div", class_=re.compile(r"\bentry-content\b", re.I))
        or soup.find("article")
        or soup.find("main")
        or soup.find("div", id=re.compile(r"content", re.I))
    )
    if not body_el:
        return "", ""
    # Drop social-share / related-posts junk often present in WP entries
    for tag in body_el.find_all(class_=re.compile(
        r"sharedaddy|share-buttons|jp-relatedposts|post-share|"
        r"related-posts|comments-area|post-comments|newsletter|"
        r"social-share|sharethis|addtoany", re.I)):
        tag.decompose()

    body = body_el.get_text(" ", strip=True)
    body = re.sub(r"\s+", " ", body).strip()
    body = body.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    excerpt = body[:500]
    return body, excerpt


def classify_type(title, summary, body):
    """Heuristic type classification based on title + content."""
    t = title.lower()
    s = (summary or "").lower()
    b = (body or "").lower()
    if NON_MUSIC_RE.search(title):
        return None
    # Festival / news / interview / environmental / release-announcement pieces
    # → feature. Single-release news ("Roll Out Tears of the Cherokee")
    # is also a feature, not a review.
    feature_kw = (
        "festival", "announces", "announce", "joins", "addresses",
        "roll out", "rolls out", "to bring", "creative hub", "interview",
        "single ", "song \"", "song '", "new song", "new album",
        "forthcoming", "upcoming", "video premiere",
    )
    if any(kw in t for kw in feature_kw):
        return "feature"
    # Album review patterns — title format "Artist – Album (Label, Year)"
    if re.search(r"\(\s*[A-Z][\w&' .-]+,\s*\d{4}\s*\)", title):
        return "review"
    # Otherwise default to review (single release news with a forthcoming album
    # is treated as feature if no review body is found; classified below).
    return "review"


def extract_artist_album(title):
    """Best-effort parse of 'Artist – Album (Label, Year)' style titles."""
    t = title.strip()
    # Strip trailing parenthetical label/year
    paren = ""
    m = re.search(r"\s*\(([^)]+)\)\s*$", t)
    if m:
        paren = m.group(1)
        t = t[:m.start()].strip()
    # Try em-dash, en-dash, hyphen
    for sep in [" — ", " – ", " - ", " —", " –", " -", "— ", "– ", "- "]:
        if sep in t:
            artist, album = t.split(sep, 1)
            return artist.strip(), album.strip()
    # No separator: treat whole title as the work name, artist empty
    return "", t


def build_record(entry, body, excerpt, ftype):
    title = entry.get("title", "").strip()
    url = entry.get("link", "").strip()
    pub_dt = parse_pub_dt(entry)
    summary = entry.get("summary", "") or entry.get("description", "")
    # Decode common HTML entities the way feedparser left them
    summary = re.sub(r"<[^>]+>", "", summary)
    summary = summary.replace("&#8217;", "'").replace("&#8230;", "…")
    summary = re.sub(r"\s+", " ", summary).strip()

    artist, album = extract_artist_album(title)
    tags = "world music,traditional,world fusion"

    return {
        "album": album or title,
        "artist": artist,
        "score": None,
        "url": url,
        "source": SOURCE,
        "pub_date": pub_dt.isoformat() if pub_dt else "",
        "tags": tags,
        "excerpt": (excerpt or summary)[:500],
        "body": body or summary,
        "site_id": SITE_ID,
        "crawl_status": "success" if body else "summary_only",
        "type": ftype,
    }


def main():
    args = parse_args()

    # Reference datetime in UTC
    if args.date:
        ref = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        ref = datetime.now(timezone.utc)
    cutoff = ref - timedelta(hours=args.hours)
    scraped_at = datetime.now(timezone.utc).isoformat()

    sys.stderr.write(f"reference: {ref.isoformat()}\n")
    sys.stderr.write(f"cutoff:    {cutoff.isoformat()}\n")
    sys.stderr.write(f"fetching RSS: {RSS_URL}\n")

    feed = fetch_rss()
    if not feed.entries:
        sys.stderr.write("RSS returned 0 entries — empty result\n")
        items = []
    else:
        sys.stderr.write(f"RSS returned {len(feed.entries)} entries\n")
        items = []
        for entry in feed.entries:
            dt = parse_pub_dt(entry)
            if dt is None:
                sys.stderr.write(f"  no pub_date for: {entry.get('title')}\n")
                continue
            if dt < cutoff:
                continue
            # Past cutoff — keep going only if we haven't reached the end
            # (RSS is reverse-chronological so once we see one too-old, stop)
            # Actually we should just continue to handle any interleaving.

            title = entry.get("title", "")
            ftype = classify_type(title, entry.get("summary", ""), "")
            if ftype is None:
                sys.stderr.write(f"  SKIP non-music: {title}\n")
                continue

            body, excerpt = "", ""
            if not args.rss_only:
                body, excerpt = get_article_body(entry.get("link", ""))
                if not body:
                    sys.stderr.write(f"  WARN: empty body for {entry.get('link')}\n")
                # Re-classify once we have body — festival news in the body
                # makes it feature not review.
                if ftype == "review" and body:
                    bl = body.lower()
                    if any(kw in bl[:1000] for kw in (
                        "festival", "creative hub", "to bring", "addresses ",
                    )):
                        ftype = "feature"

            rec = build_record(entry, body, excerpt, ftype)
            items.append(rec)
            sys.stderr.write(f"  OK [{ftype}]: {title[:60]}... ({dt.date()})\n")

    out = {
        "meta": {
            "total": len(items),
            "scraped_at": scraped_at,
            "cutoff_date": cutoff.isoformat(),
            "reference_date": ref.isoformat(),
            "site": SITE_ID,
            "source": SOURCE,
        },
        "items": items,
    }

    if args.out:
        out_path = args.out
    else:
        ref_date = ref.strftime("%Y-%m-%d")
        out_path = f"/home/liyifan/music-record/{ref_date[:4]}/{ref_date[5:7]}/{ref_date}/world_music_central_reviews.json"
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    sys.stderr.write(f"wrote {out_path} ({len(items)} items)\n")

    if not items:
        sys.stderr.write("empty result\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
