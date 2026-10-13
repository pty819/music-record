#!/usr/bin/env python3
"""
scrape_jazztokyo_rss.py — RSS-driven JazzTokyo scraper.

Used in preference to scrape_jazztokyo.py (Camoufox) when the
jazztokyo.org /feed/ endpoint is reachable. Per task spec:
"RSS 优先: 先 curl + feedparser, 有近期条目就不开浏览器".

Site: https://jazztokyo.org/  (feed at /feed/)
Genres: jazz, free improvisation, free jazz, japanese jazz

Output schema (must match scrape_jazztokyo.py):
{"meta": {total, scraped_at, cutoff_date, site, ...}, "items": [...]}
"""
import argparse
import feedparser
import html
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

SITE_BASE = "https://jazztokyo.org"
SITE_ID = "jazztokyo"
SOURCE = "JazzTokyo"
TAGS_DEFAULT = "jazz,free improvisation,free jazz,japanese jazz"
FEED_URL = f"{SITE_BASE}/feed/"

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|UHD|VOD|DVD|Blu-ray|4K)\)", re.I)

# Same path-based type classification as scrape_jazztokyo.py
REVIEW_PATH_PARTS = (
    "/reviews/cd-dvd-review/",
    "/reviews/live-report/",
    "/reviews/books/",
    "/reviews/sound-check/",
)
FEATURE_PATH_PARTS = (
    "/interviews/",
    "/column/",
    "/monthly-editorial/",
    "/news/",
    "/features/",
)

TITLE_NUM_RE = re.compile(r"^#\d+\s*")


def classify_article(url):
    path = urllib.parse.urlparse(url).path
    for p in REVIEW_PATH_PARTS:
        if p in path:
            return "review"
    for p in FEATURE_PATH_PARTS:
        if p in path:
            return "feature"
    return "feature"


def clean_url(raw):
    """Drop utm_* query params; keep canonical path."""
    if not raw:
        return ""
    try:
        u = urllib.parse.urlparse(raw)
        # Drop known tracking params
        qd = urllib.parse.parse_qs(u.query, keep_blank_values=False)
        for k in list(qd.keys()):
            if k.lower().startswith("utm_"):
                qd.pop(k, None)
        new_q = urllib.parse.urlencode({k: v[0] for k, v in qd.items()}, doseq=False)
        return urllib.parse.urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, ""))
    except Exception:
        return raw


def html_to_text(s):
    if not s:
        return ""
    # Strip tags
    s = re.sub(r"<[^>]+>", " ", s)
    # Decode entities
    s = html.unescape(s)
    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_title(raw_title):
    """Return (artist, album) — same rules as the Camoufox scraper."""
    if not raw_title:
        return "", ""
    t = TITLE_NUM_RE.sub("", raw_title).strip()
    t = re.sub(r"\s+", " ", t)
    # Book: "X 著『Y』"
    m = re.match(r"^([^『』「」]+?)著『([^』]+)』", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # CD/DVD: "『ARTIST／Album』"
    m = re.search(r"『([^』]+?)／([^』]+?)』", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Event: "DATE NAME at PLACE"
    if re.match(r"^[\d/]+\s*[～~\-]", t) or " at " in t:
        return "", t
    # "ARTIST with/feat/x/〜"
    m = re.match(
        r"^(?P<artist>[^『』「」]+?)(?:\s+(?:with|feat|×|x)\s+|\s*[〜~]\s*)(?P<rest>.+)", t
    )
    if m and len(m.group("artist")) < 60:
        return m.group("artist").strip(), m.group("rest").strip()
    return "", t


def entry_pubdate(entry):
    """Return datetime_utc or None.

    Prefer parsing the raw published/updated RFC822 string (carries explicit
    +0000 tz).  Falling back to feedparser's *parsed structs is wrong when
    the host runs in a non-UTC timezone: struct_time has no tz field, so
    mktime() interprets it as local time and silently shifts by hours.
    """
    from email.utils import parsedate_to_datetime

    for raw_attr in ("published", "updated"):
        raw = (getattr(entry, raw_attr, "") or "").strip()
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            dt = None
        if dt is None:
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    break
                except Exception:
                    continue
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    return None


def get_body(entry):
    """Prefer content:encoded; fall back to summary; return plain text."""
    raw = ""
    if hasattr(entry, "content") and entry.content:
        for c in entry.content:
            v = c.get("value", "") if isinstance(c, dict) else getattr(c, "value", "")
            if v and len(v) > len(raw):
                raw = v
    if not raw and getattr(entry, "summary", ""):
        raw = entry.summary
    if not raw and getattr(entry, "description", ""):
        raw = entry.description
    return html_to_text(raw)


def get_tags_from_categories(entry):
    cats = []
    tags_attr = getattr(entry, "tags", None)
    if not isinstance(tags_attr, list):
        return cats
    for c in tags_attr:
        term = c.get("term") if isinstance(c, dict) else getattr(c, "term", None)
        if term:
            cats.append(term)
    return cats


def main():
    ap = argparse.ArgumentParser(description="Scrape JazzTokyo via RSS")
    ap.add_argument("--days", type=float, default=1.5)
    ap.add_argument("--out-dir", type=str,
                    default=os.environ.get("HERMES_KANBAN_WORKSPACE",
                                           "/home/liyifan/music-record/2026/06/2026-06-18"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=args.days)

    sys.stderr.write(
        f"JazzTokyo RSS scraper — now={now.isoformat()} cutoff={cutoff_date.isoformat()} "
        f"days={args.days}\n"
    )

    try:
        feed = feedparser.parse(FEED_URL)
    except Exception as e:
        sys.stderr.write(f"ERROR: feedparser failed: {e}\n")
        _write_empty(args, now, cutoff_date, note=f"feedparser failed: {e}")
        return

    entries = feed.entries if hasattr(feed, "entries") else []
    if not entries:
        sys.stderr.write("WARN: feed has 0 entries\n")
        _write_empty(args, now, cutoff_date, note="Feed has 0 entries")
        return

    sys.stderr.write(f"Feed: {len(entries)} entries; bozo={getattr(feed, 'bozo', False)}\n")

    results = []
    kept = 0
    skipped_non_music = 0
    skipped_old = 0
    skipped_no_date = 0

    for n, entry in enumerate(entries, 1):
        url = clean_url(entry.get("link", ""))
        title = (entry.get("title", "") or "").strip()
        if not url or not title:
            continue

        if NON_MUSIC_RE.search(title):
            sys.stderr.write(f" [{n}] SKIP non-music (title): {title[:60]}\n")
            skipped_non_music += 1
            continue

        body_text = get_body(entry)
        if NON_MUSIC_RE.search((title + " " + body_text)[:1500]):
            sys.stderr.write(f" [{n}] SKIP non-music (body): {title[:60]}\n")
            skipped_non_music += 1
            continue

        pub_date = entry_pubdate(entry)
        if pub_date is None:
            sys.stderr.write(f" [{n}] SKIP no-date: {title[:60]}\n")
            skipped_no_date += 1
            continue

        if pub_date < cutoff_date:
            # Old — quietly stop iterating (feed is reverse-chrono)
            sys.stderr.write(f" [{n}] STOP old (pub={pub_date.date()}): {title[:50]}\n")
            skipped_old += 1
            break

        type_ = classify_article(url)
        artist, album = split_title(title)
        if not album:
            album = title

        cats = get_tags_from_categories(entry)
        tags_str = ", ".join(cats) if cats else TAGS_DEFAULT

        excerpt = body_text[:500] if body_text else ""
        item = {
            "album": album,
            "artist": artist,
            "score": None,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date.isoformat(),
            "tags": tags_str,
            "excerpt": excerpt,
            "body": body_text,
            "site_id": SITE_ID,
            "crawl_status": "ok",
            "type": type_,
        }
        results.append(item)
        kept += 1
        sys.stderr.write(
            f" [{n}] KEPT ({type_}, {pub_date.date()}): {title[:60]}\n"
        )

    sys.stderr.write(
        f"\nResults: total={len(results)} in_window={kept} "
        f"non_music_skipped={skipped_non_music} old_skipped={skipped_old} "
        f"no_date_skipped={skipped_no_date}\n"
    )

    meta = {
        "total": len(results),
        "scraped_at": now.isoformat(),
        "cutoff_date": cutoff_date.isoformat(),
        "site": SITE_ID,
        "feed_url": FEED_URL,
        "feed_entries_total": len(entries),
        "in_window_count": kept,
        "non_music_skipped": skipped_non_music,
        "old_skipped": skipped_old,
        "no_date_skipped": skipped_no_date,
        "crawl_mode": "rss",
    }
    out = {"meta": meta, "items": results}

    if args.dry_run:
        print(json.dumps(meta, indent=2, ensure_ascii=False))
        for it in results:
            print(f"  {it['pub_date']}  [{it['type']}]  {it['artist']}  {it['album']}",
                  file=sys.stderr)
        return

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "jazztokyo_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"Wrote {out_path} ({len(results)} items)\n")


def _write_empty(args, now, cutoff_date, note=""):
    out = {
        "meta": {
            "total": 0,
            "scraped_at": now.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "site": SITE_ID,
            "note": note or "No items extracted",
            "crawl_mode": "rss",
        },
        "items": [],
    }
    if args.dry_run:
        print(json.dumps(out["meta"], indent=2, ensure_ascii=False))
        return
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "jazztokyo_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"Wrote {out_path} (0 items)\n")


if __name__ == "__main__":
    main()
