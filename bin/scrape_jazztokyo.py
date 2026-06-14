#!/usr/bin/env python3
"""
scrape_jazztokyo.py — Camoufox-based scraper for JazzTokyo.

Site: https://jazztokyo.org/
Genres: jazz, free improvisation, free jazz, japanese jazz
RSS: (none)

Structure (WordPress):
 - Front page (/) and /page/2/, /page/3/... show latest posts in reverse-chrono order.
 - Each post URL is /<section>/post-<id>/ (sections: reviews/cd-dvd-review,
   reviews/live-report, interviews, column/<slug>, monthly-editorial, news).
 - Date is in <time datetime="YYYY-MM-DDTHH:MM:SS+TZ">YEAR年M月D日</time>.
 - Body is in `article` element innerText; need to drop nav/share/footer noise.
 - No RSS, no cookie wall (CF challenge only).

Filter rules:
 - 36h cutoff (--days 1.5).
 - Skip BLU-RAY / UHD / VOD / DVD content in title.
 - News posts: type=feature, score=null (they're editorial news/features).
 - Album reviews (CD/DVD Disks): type=review with possible score.
 - Live reports: type=review.
 - Interviews: type=feature.

Output schema (canonical, must match RSS + other HTML scripts):
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
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
SITE_BASE = "https://jazztokyo.org"
HOME_URL = f"{SITE_BASE}/"

SITE_ID = "jazztokyo"
SOURCE = "JazzTokyo"
TAGS_DEFAULT = "jazz,free improvisation,free jazz,japanese jazz"
USER_ID = "scraper_jazztokyo"
SESSION_KEY = "sess_jazztokyo"

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|UHD|VOD|DVD|Blu-ray|4K)\)", re.I)

# Japanese date strings like "2026年6月7日" or "2026年6月7日 ～ 8日"
JP_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
# ISO datetime from <time datetime="...">
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})")

# Article URL pattern
POST_URL_RE = re.compile(r"^/(?:[a-z-]+/)*post-(\d+)/?$")


# ── HTTP helper (Camoufox REST) ────────────────────────────────────────

def _api(method, path, body=None, timeout=60):
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
        raise RuntimeError(f"HTTP {e.code} on {method} {path}: {e.read().decode()[:200]}")
    except Exception as e:
        raise RuntimeError(f"{method} {path}: {e}")


# ── Date parsing ───────────────────────────────────────────────────────

def parse_pub_date(time_attr, time_text, body_text):
    """Return (datetime_utc, raw_string) or (None, raw_string)."""
    if time_attr:
        m = ISO_DATE_RE.search(time_attr)
        if m:
            try:
                y, mo, d, h, mi, s = map(int, m.groups())
                # Try with tz offset if present
                tz_match = re.search(r"([+-])(\d{2}):(\d{2})$", time_attr)
                if tz_match:
                    sign = 1 if tz_match.group(1) == "+" else -1
                    offset_minutes = sign * (int(tz_match.group(2)) * 60 + int(tz_match.group(3)))
                    tz_off = timezone(timedelta(minutes=offset_minutes))
                else:
                    tz_off = timezone.utc
                return datetime(y, mo, d, h, mi, s, tzinfo=tz_off), time_attr
            except Exception:
                pass
    # Fall back to Japanese date in text
    for src in (time_text or "", body_text or "")[:500]:
        m = JP_DATE_RE.search(src)
        if m:
            try:
                y, mo, d = map(int, m.groups())
                return datetime(y, mo, d, 12, 0, 0, tzinfo=timezone.utc), f"{y}-{mo:02d}-{d:02d}"
            except Exception:
                pass
    return None, time_text or ""


# ── Listing parser ─────────────────────────────────────────────────────

def extract_post_links(html_or_eval_result):
    """From a list of {h, t} links, return unique /post-N/ URLs with their titles."""
    seen = set()
    out = []
    if isinstance(html_or_eval_result, dict):
        arr = html_or_eval_result.get("result") or []
    else:
        arr = html_or_eval_result or []
    for item in arr:
        h = (item.get("h") or "").strip()
        t = (item.get("t") or "").strip()
        if not h:
            continue
        # Normalize: drop anchors, anchors with #, comment links
        if "#" in h:
            h = h.split("#", 1)[0]
        if not h.startswith("/") and not h.startswith("http"):
            continue
        # Match /post-XXXXX/ pattern
        path = urllib.parse.urlparse(h).path if h.startswith("http") else h
        if not POST_URL_RE.match(path):
            continue
        url = h if h.startswith("http") else f"{SITE_BASE}{path}"
        # Skip duplicate URLs
        if url in seen:
            continue
        seen.add(url)
        # Title: prefer non-empty text. If empty, fetch on detail page later.
        out.append({"url": url, "title": t, "path": path})
    return out


def scrape_listing(tab_id, page_url):
    """Navigate to a listing page and return candidate post links."""
    sys.stderr.write(f"\n=== Listing {page_url} ===\n")
    _api("POST", f"/tabs/{tab_id}/navigate", {"url": page_url})
    time.sleep(3)
    eval_resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "() => { const a = Array.from(document.querySelectorAll('a[href]')); const out = []; const seen = new Set(); for (const x of a) { let h = x.getAttribute('href') || ''; if (!h || h.startsWith('#')) continue; const t = (x.innerText || '').trim(); const path = h.startsWith('http') ? new URL(h).pathname : h; if (!/^\\/[\\w-]+(\\/[\\w-]+)?\\/post-\\d+\\/?$/.test(path)) continue; const full = h.startsWith('http') ? h : ('https://jazztokyo.org' + path); if (seen.has(full)) continue; seen.add(full); out.push({h: full, t: t.slice(0, 200)}); } return out; }"
    })
    links = extract_post_links(eval_resp)
    sys.stderr.write(f"  found {len(links)} post links\n")
    return links


# ── Article body parser ────────────────────────────────────────────────

def parse_article(tab_id, url):
    """Fetch an article page; return dict with title, time, time_attr, body_text."""
    sys.stderr.write(f"  fetch: {url}\n")
    _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
    time.sleep(2)
    resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "() => { const art = document.querySelector('article') || document.querySelector('.entry-content') || document.querySelector('.post') || document.body; const h1s = Array.from(document.querySelectorAll('article h1, .entry-title, h1.post-title, h1')); const t = h1s.length ? h1s.reduce((a,b)=>(b.innerText||'').length>(a.innerText||'').length?b:a) : null; const time = document.querySelector('time'); const cat = document.querySelector('.cat-links a, .category a, .post-categories a'); return { title: t && (t.innerText||'').trim(), timeAttr: time && time.getAttribute('datetime'), timeText: time && (time.innerText||'').trim(), category: cat && (cat.innerText||'').trim(), body: art ? (art.innerText||'') : '' }; }"
    })
    res = resp.get("result") or {}
    body = res.get("body") or ""
    # Strip noise: bottom-of-page share widgets, comment prompts, "共有:" lines
    body = re.split(r"\n\s*共有:", body, maxsplit=1)[0]
    body = re.split(r"\n\s*コメントをどうぞ", body, maxsplit=1)[0]
    body = re.sub(r"\n\s*\d+\s*件のコメント.*$", "", body, flags=re.S)
    body = re.sub(r"\n\s*コメントは.*$", "", body, flags=re.S)
    body = body.strip()
    return {
        "url": url,
        "title": res.get("title") or "",
        "time_attr": res.get("timeAttr") or "",
        "time_text": res.get("timeText") or "",
        "category": res.get("category") or "",
        "body": body,
    }


# ── Type classification ────────────────────────────────────────────────

def classify_article(url, title, category):
    """Return type ∈ {review, feature} based on URL path."""
    path = urllib.parse.urlparse(url).path
    if "/reviews/cd-dvd-review/" in path:
        return "review"
    if "/reviews/live-report/" in path:
        return "review"
    if "/reviews/books/" in path:
        return "review"
    if "/reviews/sound-check/" in path:
        return "review"
    if "/interviews/" in path:
        return "feature"
    if "/column/" in path:
        return "feature"
    if "/monthly-editorial/" in path:
        return "feature"
    if "/news/" in path:
        return "feature"
    if "/features/" in path:
        return "feature"
    return "feature"


# ── Title parsing ──────────────────────────────────────────────────────

# Title format examples from listing:
#   "#2441 『挾間美帆／Frames』『Miho Hazama／Frames』"  (CD review)
#   "#1409 中川英二郎 TRAD JAZZ COMPANY with 北村英治〜ラ・フォル・ジュルネTOKYO 2026『大河』"  (live)
#   "7/30 東かおる、柳原由佳、沢田穣治 at 大阪・天満 Bamboo Club"  (news)
#   "小川隆夫著『マイルス・デイヴィス大百科』刊行"  (news)
#   "インプロヴァイザーの立脚地 vol.40  ミドリトモヒデ"  (interview)
TITLE_NUM_RE = re.compile(r"^#\d+\s*")
TITLE_BOOK_RE = re.compile(r"^(?P<artist>[^『』「」]+?)著『(?P<album>[^』]+)』")

def split_title(raw_title, url):
    """Return (artist, album). For news/columns both may be derived from title."""
    if not raw_title:
        return "", ""
    t = TITLE_NUM_RE.sub("", raw_title).strip()
    t = re.sub(r"\s+", " ", t)
    # Book review: "X 著『Y』..."  → artist=X, album=Y
    m = TITLE_BOOK_RE.match(t)
    if m:
        return m.group("artist").strip(), m.group("album").strip()
    # CD/DVD review: "『ARTIST／Album』" or "『ARTIST / Album』"
    m = re.search(r"『([^』]+?)／([^』]+?)』", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.search(r"『([^』]+?)／([^』]+?)』", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Event: "DATE NAME at PLACE" — use full title as album, no artist
    if re.match(r"^[\d/]+\s*[～~\-]", t) or " at " in t.lower() or " at " in t:
        return "", t
    # "ARTIST feat ..." or "ARTIST with ..."
    m = re.match(r"^(?P<artist>[^『』「」]+?)(?:\s+(?:with|feat|×|x)\s+|\s*[〜~]\s*)(?P<rest>.+)", t)
    if m and len(m.group("artist")) < 60:
        return m.group("artist").strip(), m.group("rest").strip()
    # Column / news: title is the "album"
    return "", t


# ── Main ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Scrape JazzTokyo")
    ap.add_argument("--days", type=float, default=1.5)
    ap.add_argument("--out-dir", type=str,
        default=os.environ.get("HERMES_KANBAN_WORKSPACE", "/home/liyifan/music-record/2026/06/2026-06-14"))
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--max-articles", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=args.days)

    sys.stderr.write(
        f"JazzTokyo scraper — now={now.isoformat()} cutoff={cutoff_date.isoformat()} "
        f"days={args.days}\n"
    )

    # 1. Create tab
    try:
        tab_resp = _api("POST", "/tabs", {
            "userId": USER_ID,
            "sessionKey": SESSION_KEY,
            "url": HOME_URL,
        }, timeout=90)
    except Exception as e:
        sys.stderr.write(f"ERROR: failed to create tab: {e}\n")
        _write_empty(args, now, cutoff_date, note=f"Tab creation failed: {e}")
        return

    tid = tab_resp.get("tabId")
    if not tid:
        sys.stderr.write("ERROR: no tabId\n")
        _write_empty(args, now, cutoff_date, note="No tabId returned")
        return

    try:
        # CF challenge settle
        time.sleep(6)

        # 2. Collect links from front 2 pages
        candidate_urls = {}  # url -> {"title": ..., "source": ...}
        pages = [HOME_URL, f"{SITE_BASE}/page/2/"][:args.max_pages]
        for label, page_url in zip(["p1", "p2"], pages):
            for link in scrape_listing(tid, page_url):
                if link["url"] not in candidate_urls:
                    candidate_urls[link["url"]] = {"title": link["title"], "source": label}

        sys.stderr.write(f"\nTotal unique candidates: {len(candidate_urls)}\n")

        # 3. Fetch each article; apply filters
        results = []
        kept = 0
        skipped_non_music = 0
        skipped_old = 0
        fetch_errors = 0

        ordered = list(candidate_urls.items())[:args.max_articles]

        for n, (url, meta) in enumerate(ordered, 1):
            list_title = meta["title"]
            # Pre-filter: skip BLU-RAY/UHD/VOD/DVD in listing title
            if NON_MUSIC_RE.search(list_title):
                sys.stderr.write(f" [{n}/{len(ordered)}] SKIP non-music (list): {list_title[:60]}\n")
                skipped_non_music += 1
                continue

            try:
                art = parse_article(tid, url)
            except Exception as e:
                sys.stderr.write(f" [{n}/{len(ordered)}] FETCH ERROR: {url} {e}\n")
                fetch_errors += 1
                continue

            full_text = (art["title"] + "\n" + art["body"])
            if NON_MUSIC_RE.search(full_text[:1500]):
                sys.stderr.write(f" [{n}/{len(ordered)}] SKIP non-music (body): {url}\n")
                skipped_non_music += 1
                continue

            pub_date, raw_date = parse_pub_date(art["time_attr"], art["time_text"], art["body"])
            if pub_date is None:
                sys.stderr.write(f" [{n}/{len(ordered)}] SKIP no-date: {url}\n")
                fetch_errors += 1
                continue

            if pub_date < cutoff_date:
                sys.stderr.write(f" [{n}/{len(ordered)}] SKIP old (pub={pub_date.date()}): {art['title'][:50]}\n")
                skipped_old += 1
                continue

            type_ = classify_article(url, art["title"], art["category"])
            artist, album = split_title(art["title"], url)
            if not album:
                album = art["title"] or list_title

            excerpt = art["body"][:500].replace("\n", " ") if art["body"] else ""

            item = {
                "album": album,
                "artist": artist,
                "score": None,
                "url": url,
                "source": SOURCE,
                "pub_date": pub_date.isoformat(),
                "tags": TAGS_DEFAULT,
                "excerpt": excerpt,
                "body": art["body"],
                "site_id": SITE_ID,
                "crawl_status": "ok",
                "type": type_,
            }
            results.append(item)
            kept += 1
            sys.stderr.write(f" [{n}/{len(ordered)}] KEPT ({type_}, {pub_date.date()}): {art['title'][:60]}\n")

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
                "pages_crawled": min(args.max_pages, len(pages)),
                "candidates_checked": len(ordered),
                "in_window_count": kept,
                "non_music_skipped": skipped_non_music,
                "old_skipped": skipped_old,
                "fetch_errors": fetch_errors,
            },
            "items": results,
        }

        if args.dry_run:
            print(json.dumps(out["meta"], indent=2, ensure_ascii=False))
            return

        os.makedirs(args.out_dir, exist_ok=True)
        out_path = os.path.join(args.out_dir, "jazztokyo_reviews.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"Wrote {out_path} ({len(results)} items)\n")

    finally:
        try:
            _api("DELETE", f"/tabs/{tid}")
        except Exception as e:
            sys.stderr.write(f"WARN: failed to close tab: {e}\n")


def _write_empty(args, now, cutoff_date, note=""):
    out = {
        "meta": {
            "total": 0,
            "scraped_at": now.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "site": SITE_ID,
            "note": note or "No items extracted",
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