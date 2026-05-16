#!/usr/bin/env python3
"""Scrape Avant Music News - extract reviews from RSS feed within 3-day window."""

import feedparser
import json
import re
import html
from datetime import datetime, timezone, timedelta
from html import unescape

# ── config ──────────────────────────────────────────────────────────────────
FEED_URL = "https://avantmusicnews.com/feed/"
SITE_ID  = "avant_music_news"
TAGS     = ["experimental", "weird", "progressive", "avant-garde"]
OUT_PATH = "/home/liyifan/music-record/2026/05/2026-05-16/avant_music_news_reviews.json"

NOW        = datetime.now(timezone.utc)
THREE_DAYS = NOW - timedelta(days=3)

VIDEO_RE = re.compile(
    r"\b(BLU-RAY|BLU\s*RAY|UHD|VOD|DVD|Blu-ray)\b", re.IGNORECASE
)

def parse_rss_date(date_str: str):
    try:
        date_str = re.sub(r"^[A-Z][a-z]{2},\s*", "", date_str)
        return datetime.strptime(date_str.strip(), "%d %b %Y %H:%M:%S %z")
    except Exception:
        return None

def parse_roundup_date(date_str: str):
    try:
        return datetime.strptime(date_str.strip(), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def make_excerpt(raw_text: str, max_chars: int = 500) -> str:
    if not raw_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text

def in_window(entry) -> bool:
    pub_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pub_parsed:
        return False
    try:
        dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
        return dt >= THREE_DAYS
    except Exception:
        return False

def guess_type(title: str, summary: str) -> str:
    combined = (title + " " + summary).lower()
    if any(k in combined for k in [
        "interview", "label profile", "coming to", "tour",
        "radio as instrument", "profiled", "list", "best of",
        "essays", "thinkpiece", "at 25", "new releases"
    ]):
        return "feature"
    return "review"

def make_result(artist, album, label, pub_date_str, reviewer, source, raw, entry):
    if VIDEO_RE.search(artist) or VIDEO_RE.search(album):
        return None
    entry_pub = entry.get("published", "")
    entry_dt  = parse_rss_date(entry_pub)
    cutoff    = entry_dt - timedelta(days=3) if entry_dt else None

    idate = parse_roundup_date(pub_date_str) if pub_date_str else None
    final_date = idate.isoformat() if idate else entry_pub

    if cutoff:
        try:
            check_dt = datetime.fromisoformat(final_date)
            if check_dt < cutoff:
                return None
        except Exception:
            pass

    return {
        "album":        album.strip(),
        "artist":       artist.strip(),
        "score":        None,
        "url":          entry.get("link", ""),
        "source":       source,
        "pub_date":     final_date,
        "tags":         TAGS,
        "excerpt":      make_excerpt(raw[:600]),
        "site_id":      SITE_ID,
        "crawl_status": "success",
        "type":         "review",
    }


# ── Dusted / Wire style ──────────────────────────────────────────────────────
# "May 14, 2026 — Artist, "Album" (Label) reviewed by Reviewer."
REVIEW_PAT1 = re.compile(
    r"([A-Z][a-z]+ \d{1,2}, \d{4})"
    r"\s*[—–-]\s*"
    r"([^,]+)\s*,\s*"
    r"[\"\u201c\u201d\u2018\u2019]([^\"\u201c\u201d\u2018\u2019]+)[\"\u201c\u201d\u2018\u2019]"
    r"\s*\(([^)]+)\)"
    r"(?:\s*reviewed by ([^.]+))?",
    re.IGNORECASE
)


# ── Psychotropic Wonderland style ──────────────────────────────────────────
# "(May 12, 2026) — Artist, "Album" (Label, Year)"
REVIEW_PAT2 = re.compile(
    r"\(([A-Z][a-z]+ \d{1,2}, \d{4})\)\s*[—–-]\s*"
    r"(?:\[https?://[^\]]+\]\s*)?"
    r"([^,]+?)\s*,\s*"
    r"[\"\u201c\u201d\u2018\u2019]([^\"\u201c\u201d\u2018\u2019]+)[\"\u201c\u201d\u2018\u2019]"
    r"\s*\(([^)]+)\)",
    re.IGNORECASE
)


# ── Free Jazz Collective style ──────────────────────────────────────────────
# "Artist – Album (Label, Year) reviewed by Reviewer."
FREE_JAZZ_PAT = re.compile(
    r'\.\s*reviewed by\s*',
    re.IGNORECASE
)


def parse_free_jazz(text: str) -> list[dict]:
    """
    Free Jazz Collective: 'Artist – Album (Label) reviewed by Reviewer. ...'
    Also: 'Artist (extra) – Album (Label) reviewed by Reviewer.'
    Returns list of {'artist', 'album', 'label', 'reviewer'}.
    """
    results = []
    for m in FREE_JAZZ_PAT.finditer(text):
        before = text[:m.start()].strip()
        after  = text[m.end():].strip()

        # Extract artist-album from before: last 'Artist – Album (Label)' before '.'
        artist_album_m = None
        for am in re.finditer(r'(.+?)\s*[–—]\s*(.+?)\s*\(([^)]+)\)\s*$', before):
            artist_album_m = am
        if not artist_album_m:
            continue

        artist_full = artist_album_m.group(1).strip()
        album       = artist_album_m.group(2).strip()
        label_year  = artist_album_m.group(3).strip()
        artist = re.sub(r'\s*\([^)]*\)\s*$', '', artist_full).strip()

        # Extract reviewer from after (everything before next '.')
        reviewer = re.sub(r'\..*$', '', after).strip()

        results.append({
            'artist': artist,
            'album': album,
            'label': label_year,
            'reviewer': reviewer,
        })

    return results


# ── Chain D.L.K. style ─────────────────────────────────────────────────────
def parse_chain_dlk(text: str) -> list[dict]:
    """
    Chain D.L.K.: 'Artist – Album (Label) — reviewed by Reviewer of Date Artist – ...'
    Split on ' — reviewed by', then pair artist-album segments with reviewer-date info.

    Split gives:
      segments[0] = intro + first_artist_album  (no preceding reviewer)
      segments[1] = 'Reviewer of Date Artist – Album (Label)'
      segments[2] = 'Reviewer of Date'          (last reviewer, no artist)
      ...

    Algorithm:
      - Entry i: artist-album from segments[i] (end part), reviewer+date from segments[i+1] (start part)
      - For i=0: special case - artist-album from END of segments[0], reviewer from segments[1]
    """
    results = []
    # Split on ' — reviewed by'
    segments = re.split(r'\s*—\s*reviewed by\s*', text, flags=re.IGNORECASE)
    if len(segments) < 2:
        return results

    # Process entries: segments[i] has artist for entry i, segments[i+1] has reviewer for entry i
    for i in range(len(segments) - 1):
        artist_seg = segments[i]
        reviewer_seg = segments[i + 1]

        # ── Extract artist-album from artist_seg ──────────────────
        # For i=0: artist-album is at the END of segments[0] (after last em-dash)
        # For i>0: artist-album is also at the END (the artist for entry i is embedded after date of entry i-1)
        # Actually for all i: the artist-album for entry i is the last Artist-Album pattern in artist_seg
        artist_m = None
        for am in re.finditer(r'([^\u2014—]+?)\s*–\s*(.+?)\s*\(([^)]+)\)', artist_seg):
            artist_m = am  # keep updating to get the last one
        if not artist_m:
            continue
        artist = artist_m.group(1).strip()
        album  = artist_m.group(2).strip()
        label  = artist_m.group(3).strip()

        # ── Extract reviewer+date from reviewer_seg ─────────────────
        # Format: 'Reviewer of Date Artist – Album...' or 'Reviewer of Date' (last entry)
        date_m = re.search(r'[oO][fF]\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', reviewer_seg)
        date_str = date_m.group(1) if date_m else None
        if date_m:
            reviewer = reviewer_seg[:date_m.start()].strip()
        else:
            reviewer = re.sub(r'\s*–.*$', '', reviewer_seg).strip()

        # Clean up reviewer name
        reviewer = reviewer.replace('reviewed by', '').strip()
        if not reviewer or len(reviewer) < 2:
            reviewer = None

        results.append({
            'artist':   artist,
            'album':    album,
            'label':    label,
            'reviewer': reviewer or '',
            'date':     date_str,
        })

    return results


def try_parse_review_patterns(raw: str, entry) -> list[dict]:
    results = []
    raw = html.unescape(raw)
    entry_link = entry.get("link", "")

    # ── Pattern 1: Dusted / Wire style ─────────────────────────
    for m in REVIEW_PAT1.finditer(raw):
        pub_ds, artist, album, label, reviewer = m.groups()
        r = make_result(artist, album, label, pub_ds,
                        reviewer or "",
                        f"Avant Music News / {reviewer.strip() if reviewer else label.strip()}",
                        raw, entry)
        if r:
            results.append(r)
    if results:
        return results

    # ── Pattern 2: Psychotropic Wonderland style ─────────────────
    for m in REVIEW_PAT2.finditer(raw):
        pub_ds, artist, album, label = m.groups()
        r = make_result(artist, album, label, pub_ds, "",
                        "Avant Music News / Psychotropic Wonderland",
                        raw, entry)
        if r:
            results.append(r)
    if results:
        return results

    # ── Pattern 3: Chain D.L.K. ─────────────────────────────────
    chain_results = parse_chain_dlk(raw)
    if chain_results:
        for cr in chain_results:
            r = make_result(
                cr['artist'], cr['album'], cr['label'],
                cr['date'], cr['reviewer'],
                "Avant Music News / Chain D.L.K.",
                raw, entry
            )
            if r:
                results.append(r)
        if results:
            return results

    # ── Pattern 4: Free Jazz Collective ─────────────────────────
    fj_results = parse_free_jazz(raw)
    if fj_results:
        for fj in fj_results:
            r = make_result(
                fj['artist'], fj['album'], fj['label'],
                None, fj['reviewer'],
                "Avant Music News / The Free Jazz Collective",
                raw, entry
            )
            if r:
                results.append(r)
        if results:
            return results

    return []


def extract_feature(entry, title: str) -> dict:
    raw = entry.get("summary_detail", {}).get("value", "") or entry.get("summary", "")
    raw = html.unescape(raw)
    pub_str = entry.get("published", "")
    pub_dt  = parse_rss_date(pub_str)
    pub_date = pub_dt.isoformat() if pub_dt else pub_str

    artist_name = None
    if "Label Profiled" in title:
        m = re.match(r"^([A-Z][A-Za-z\s]+?)\s+Label Profiled$", title)
        if m:
            artist_name = m.group(1).strip()
    elif "Interview" in title:
        artist_name = title.replace(" Interview", "").strip()

    return {
        "album":     title,
        "artist":    artist_name,
        "score":     None,
        "url":       entry.get("link", ""),
        "source":    "Avant Music News",
        "pub_date":  pub_date,
        "tags":      TAGS,
        "excerpt":   make_excerpt(raw[:500]),
        "site_id":   SITE_ID,
        "crawl_status": "success",
        "type":      "feature",
    }


# ── main ─────────────────────────────────────────────────────────────────────
d = feedparser.parse(FEED_URL)
print(f"RSS entries total: {len(d.entries)}")

all_reviews = []
seen_urls   = set()

for entry in d.entries:
    if not in_window(entry):
        continue

    title   = entry.get("title", "")
    summary = entry.get("summary", "")
    link    = entry.get("link", "")

    if VIDEO_RE.search(title):
        print(f"  SKIP (video): {title}")
        continue

    if link in seen_urls:
        continue
    seen_urls.add(link)

    raw = entry.get("summary_detail", {}).get("value", "") or summary

    review_items = try_parse_review_patterns(raw, entry)

    if review_items:
        all_reviews.extend(review_items)
        for item in review_items:
            print(f"  REVIEW: {item['artist']} – {item['album']} [{item['pub_date'][:10]}]")
    else:
        rtype = guess_type(title, summary)
        feat = extract_feature(entry, title)
        all_reviews.append(feat)
        if rtype == "feature":
            print(f"  FEATURE: {title} [{feat['pub_date'][:10]}]")
        else:
            print(f"  FEATURE (default): {title}")

print(f"\nTotal items: {len(all_reviews)}")
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(all_reviews, f, ensure_ascii=False, indent=2)
print(f"Written: {OUT_PATH}")
