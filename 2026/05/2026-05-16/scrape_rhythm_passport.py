import feedparser
import urllib.request
import ssl
import json
import re
from datetime import datetime, timedelta
from html import unescape

# ── config ──────────────────────────────────────────────────────────
SITE        = "rhythm_passport"
SOURCE_URL  = "https://rhythmpassport.com/"
RSS_URL     = "https://rhythmpassport.com/feed/"
TAGS        = ["world music", "folk", "roots", "crossover"]
SITE_ID     = "rhythm_passport"
CUTOFF_DAYS = 3
OUT_FILE    = "/home/liyifan/music-record/2026/05/2026-05-16/rhythm_passport_reviews.json"
# ──────────────────────────────────────────────────────────────────

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode    = ssl.CERT_NONE
req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
    raw = resp.read().decode("utf-8", errors="replace")

feed = feedparser.parse(raw)
print(f"Total RSS entries: {len(feed.entries)}")

now      = datetime.utcnow()
cutoff   = now - timedelta(days=CUTOFF_DAYS)
print(f"Cutoff date: {cutoff.date()}  (3 days ago)")

def parse_date(date_str):
    """Parse various date formats into YYYY-MM-DD."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%d %b %Y %H:%M:%S",
    ]
    date_str = date_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Try feedparser's parsed structure
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    return text.strip()

def is_non_music(artist, album):
    """Return True if this looks like DVD/Blu-ray/film review, not music."""
    keywords = ["BLU-RAY", "BLU RAY", "UHD", "VOD", "DVD", "FILM", "MOVIE", "DOCUMENTARY"]
    for kw in keywords:
        if kw in (artist or "").upper() or kw in (album or "").upper():
            return True
    return False

# ── parse entries ──────────────────────────────────────────────────
items = []
for entry in feed.entries:
    title     = entry.get("title", "")
    pub_str   = entry.get("published") or entry.get("updated") or ""
    date_str  = parse_date(pub_str)

    if not date_str:
        print(f"  SKIP (unparseable date): {title[:60]}")
        continue

    pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
    if pub_dt < cutoff:
        print(f"  TOO OLD ({date_str}): {title[:60]}")
        continue

    print(f"  IN WINDOW ({date_str}): {title[:60]}")

    # Extract full text from description/summary (feedparser CDATA field)
    summary = entry.get("summary") or entry.get("description") or ""
    full_text = strip_html(summary)
    excerpt = full_text[:500] if full_text else ""

    # Determine album / artist / type from title
    # Common patterns: "Album – Artist", "Artist: Album", "Artist – Album"
    album  = title
    artist = ""
    kind   = "feature"  # default; most RP articles are features/discoveries

    # Detect if it's a review-like format (contains "Review", score, etc.)
    is_review = False
    if re.search(r'\d+/10|\d+\s*out of', summary + title, re.IGNORECASE):
        is_review = True

    # Try to split title
    for sep in [" – ", " –", " – ", ": ", " // ", " // "]:
        if sep in title:
            parts = title.split(sep, 1)
            if len(parts) == 2:
                # Heuristic: shorter part is artist, longer is album
                p0, p1 = parts[0].strip(), parts[1].strip()
                if len(p0) < len(p1):
                    artist, album = p0, p1
                else:
                    album, artist = p0, p1
                break

    if is_non_music(artist, album):
        print(f"    NON-MUSIC skip: {title[:60]}")
        continue

    item = {
        "album":      album or title,
        "artist":     artist or "Unknown",
        "score":      None,
        "url":        (entry.get("link") or entry.get("id") or ""),
        "source":     "Rhythm Passport",
        "pub_date":   date_str,
        "tags":       TAGS,
        "excerpt":    excerpt,
        "site_id":    SITE_ID,
        "crawl_status": "success",
        "type":       "review" if is_review else "feature",
    }
    items.append(item)

print(f"\nTotal items in 3-day window: {len(items)}")
for it in items:
    print(f"  [{it['type']}] {it['pub_date']} | {it['album']} – {it['artist']}")

# ── write output ───────────────────────────────────────────────────
with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f"\nWritten {len(items)} items to {OUT_FILE}")