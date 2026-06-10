#!/usr/bin/env python3
"""
scrape_hear65.py — Hear65 (Singapore music) scraper.

Strategy:
  1. Read RSS at https://hear65.bandwagon.asia/rss/most_recent.rss (feedparser)
  2. Filter to entries within the 36h window
  3. Fetch full body of each article (server-rendered, curl + regex parse)
  4. Non-music filter: skip (BLU-RAY)/(UHD)/(VOD)/(DVD)
  5. Classify type: REVIEWS category -> "review", PLAYLISTS -> "tracklist", others -> "feature"
  6. Output {meta, items} JSON

Usage:
  python3 scrape_hear65.py
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from time import mktime
from zoneinfo import ZoneInfo

import feedparser

RSS_URL = "https://hear65.bandwagon.asia/rss/most_recent.rss"
SITE_ID = "hear65"
SOURCE = "Hear65"
TAGS = "singapore music,reviews"
SGT = ZoneInfo("Asia/Singapore")
TODAY = datetime.now(timezone.utc)
WINDOW_HOURS = 36

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

NON_MUSIC_PATTERNS = re.compile(r"\((BLU-RAY|UHD|VOD|DVD)\)", re.IGNORECASE)

# Try to classify per category shown in homepage / article body
REVIEW_CATS = {"REVIEWS", "REVIEW"}
PLAYLIST_CATS = {"PLAYLISTS", "PLAYLIST", "TRACKLIST"}


def parse_pub_dt(entry):
    """Return timezone-aware datetime, or None."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    if hasattr(entry, "published") and entry.published:
        try:
            dt = parsedate_to_datetime(entry.published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return None


def fetch_article_body(url: str) -> str:
    """Fetch the article HTML and extract the <article> body as plain text.

    The Hear65 article body is server-rendered as <article class="article ...">...</article>.
    We strip tags and collapse whitespace.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        sys.stderr.write(f"  WARN: failed to fetch {url}: {e}\n")
        return ""

    m = re.search(r"<article\b[^>]*>(.*?)</article>", html, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    inner = m.group(1)

    # Drop the share/social block and any script/style before stripping
    inner = re.sub(r"<script\b[^>]*>.*?</script>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    inner = re.sub(r"<style\b[^>]*>.*?</style>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    inner = re.sub(r"<iframe\b[^>]*>.*?</iframe>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    inner = re.sub(r"<noscript\b[^>]*>.*?</noscript>", "", inner, flags=re.DOTALL | re.IGNORECASE)

    # Convert <br> and closing block tags to newlines
    inner = re.sub(r"<(br|/p|/h[1-6]|/li|/div)\b[^>]*>", "\n", inner, flags=re.IGNORECASE)
    # Strip remaining tags
    inner = re.sub(r"<[^>]+>", "", inner)
    # Decode common entities
    inner = (inner.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                  .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
    # Collapse whitespace per line, drop empty lines
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in inner.split("\n")]
    text = "\n".join(ln for ln in lines if ln)
    return text.strip()


def classify_type(categories: list[str], title: str) -> str:
    cats_upper = {c.strip().upper() for c in categories}
    if cats_upper & REVIEW_CATS:
        return "review"
    if cats_upper & PLAYLIST_CATS:
        return "tracklist"
    if "INTERVIEW" in cats_upper or "FEATURES" in cats_upper or "FEATURE" in cats_upper or "GUIDES" in cats_upper:
        return "feature"
    return "feature"


def extract_artist_album_from_title(title: str) -> tuple[str, str]:
    """Playlist / feature titles list many artists. Treat title as 'album'-like
    (i.e. playlist/article name) and leave artist blank for non-review types.
    For REVIEWS-type titles, try to split on ' — ' or ' – '."""
    for sep in [" — ", " – ", " - "]:
        if sep in title:
            artist, album = title.split(sep, 1)
            return artist.strip(), album.strip()
    return "", title.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=WINDOW_HOURS)
    parser.add_argument("--days", type=float, default=None,
                        help="Cutoff in days (overrides --hours if set)")
    args = parser.parse_args()

    hours = args.days * 24 if args.days is not None else args.hours
    cutoff = TODAY - timedelta(hours=hours)
    sys.stderr.write(f"Hear65 scraper — now: {TODAY.isoformat()}, cutoff: {cutoff.isoformat()}\n")

    # feedparser's default urllib HTTP/1.1 client gets RemoteDisconnected; the
    # server responds fine to curl (HTTP/2). Workaround: fetch with curl, then
    # let feedparser parse the response body.
    try:
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
            tmp_path = tf.name
        subprocess.run(
            ["curl", "-sL", "--max-time", "30",
             "-A", USER_AGENT,
             RSS_URL, "-o", tmp_path],
            check=False,
        )
        with open(tmp_path, "rb") as f:
            raw = f.read()
        try:
            import os; os.unlink(tmp_path)
        except Exception:
            pass
        feed = feedparser.parse(raw)
    except Exception as e:
        sys.stderr.write(f"WARN: curl-based RSS fetch failed: {e}; falling back to direct\n")
        feed = feedparser.parse(RSS_URL, agent=USER_AGENT)
    entries = feed.entries if hasattr(feed, "entries") else []
    if not entries:
        sys.stderr.write("RSS returned 0 entries\n")
        print(json.dumps({
            "meta": {"total": 0, "scraped_at": TODAY.isoformat(),
                     "cutoff_date": cutoff.isoformat()},
            "items": [],
        }, indent=2, ensure_ascii=False))
        return

    items = []
    for entry in entries:
        pub_dt = parse_pub_dt(entry)
        if pub_dt is None:
            sys.stderr.write(f"  SKIP — unparseable pub date: {entry.get('title', '')[:60]}\n")
            continue
        if pub_dt < cutoff:
            sys.stderr.write(f"  SKIP — {pub_dt.isoformat()} predates cutoff: "
                             f"{entry.get('title', '')[:60]}\n")
            continue

        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue

        if NON_MUSIC_PATTERNS.search(title):
            sys.stderr.write(f"  SKIP — non-music pattern in title: {title[:60]}\n")
            continue

        # Get description from RSS (used as excerpt fallback)
        rss_desc = (entry.get("summary") or entry.get("description") or "").strip()
        rss_desc = re.sub(r"<[^>]+>", "", rss_desc)
        rss_desc = re.sub(r"\s+", " ", rss_desc).strip()
        rss_desc = (rss_desc.replace("&amp;", "&").replace("&quot;", '"')
                              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))

        # Try to derive categories from RSS (Hear65 RSS doesn't include <category>,
        # so we infer from title prefix and content)
        categories = []
        title_clean = title.lstrip()
        type_guess = "feature"  # default for Hear65 (interviews/features/playlists)

        # New Music This Week is a playlist
        if title_clean.lower().startswith("new music this week"):
            categories = ["PLAYLISTS"]
        # Concert / gig guides
        elif "guide" in title_clean.lower() and "concert" in title_clean.lower():
            categories = ["GUIDES"]
        # Music video guide
        elif "music video guide" in title_clean.lower():
            categories = ["GUIDES"]
        # Reviews (Hear65 has a /reviews section, but reviews come through /articles)
        elif "review" in title_clean.lower() and "album review" in title_clean.lower():
            categories = ["REVIEWS"]
        else:
            categories = ["FEATURES"]

        item_type = classify_type(categories, title_clean)
        artist, album = extract_artist_album_from_title(title_clean)

        sys.stderr.write(f"  OK — fetching body: {title[:60]} ({item_type})\n")
        body = fetch_article_body(url)

        if not body:
            body = rss_desc  # fall back to RSS description
        if not body:
            sys.stderr.write(f"    WARN: empty body for {url}\n")
        else:
            sys.stderr.write(f"    body: {len(body)} chars\n")

        excerpt = rss_desc[:500] if rss_desc else body[:500]

        items.append({
            "album": album,
            "artist": artist,
            "score": None,
            "url": url,
            "source": SOURCE,
            # Use Singapore time (Hear65's editorial timezone) so a Friday SGT
            # post doesn't get mis-stamped to Thursday UTC.
            "pub_date": pub_dt.astimezone(SGT).date().isoformat(),
            "tags": TAGS,
            "excerpt": excerpt,
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success" if body else "partial",
            "type": item_type,
        })

    items.sort(key=lambda r: r["pub_date"], reverse=True)

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": TODAY.isoformat(),
            "cutoff_date": cutoff.isoformat(),
        },
        "items": items,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"\nTotal: {len(items)} items from Hear65\n")


if __name__ == "__main__":
    main()
