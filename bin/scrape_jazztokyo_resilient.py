#!/usr/bin/env python3
"""
scrape_jazztokyo_resilient.py — JazzTokyo scraper, hardened against the two
Camoufox @askjo/camofox-browser gotchas:

1. POST /tabs returns HTTP 500 after ~30s but the tab IS created. The fix
   is to re-list tabs and reuse the freshly-created one. (The plain
   scrape_jazztokyo.py bails on the 500.)
2. POST /tabs/{id}/navigate destroys the tab on timeout. We use ONE
   fresh tab per navigation (listing page 1, listing page 2, each
   article) — never reuse across navigations.

Mirrors the structure of scrape_jazztokyo.py but with these fixes.
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
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "")
SITE_BASE = "https://jazztokyo.org"
HOME_URL = f"{SITE_BASE}/"

SITE_ID = "jazztokyo"
SOURCE = "JazzTokyo"
TAGS_DEFAULT = "jazz,free improvisation,free jazz,japanese jazz"
USER_ID = "scraper_jazztokyo_r"
SESSION_KEY = f"daily-{datetime.now(timezone.utc).date().isoformat()}-jazztokyo"

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|UHD|VOD|DVD|Blu-ray|4K)\)", re.I)
JP_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})")
POST_URL_RE = re.compile(r"^/(?:[a-z-]+/)*post-(\d+)/?$")


# ── HTTP helper ────────────────────────────────────────────────────────

def _api(method, path, body=None, timeout=60):
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {}
    if data:
        headers["Content-Type"] = "application/json"
    if CAMOFOX_API_KEY:
        headers["Authorization"] = f"Bearer {CAMOFOX_API_KEY}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return None, str(e)


def _api_post_status_code(method, path, body=None, timeout=60):
    """Return (status, body) for any HTTP response, parsing JSON if possible."""
    return _api(method, path, body, timeout)


# ── Tab management (resilient) ─────────────────────────────────────────

def create_tab_resilient(url, user_id, session_key, max_wait_s=90):
    """POST /tabs but tolerate 500 — the tab may have been created (but the
    URL navigation may not have happened, leaving the tab at about:blank).
    Returns tab_id or None.
    """
    status, body = _api("POST", "/tabs", {
        "userId": user_id, "sessionKey": session_key, "url": url
    }, timeout=max_wait_s)
    if status == 200 and isinstance(body, dict) and body.get("tabId"):
        sys.stderr.write(f"  [tab] created OK ({body['tabId']})\n")
        return body["tabId"]
    sys.stderr.write(f"  [tab] POST /tabs returned {status}: {str(body)[:200]}\n")
    # Recover by listing tabs
    sys.stderr.write("  [tab] checking existing tabs...\n")
    s, b = _api("GET", f"/tabs?userId={user_id}&sessionKey={session_key}")
    recovered_id = None
    if s == 200 and isinstance(b, dict):
        for t in b.get("tabs", []):
            if t.get("listItemId") == session_key:
                sys.stderr.write(
                    f"  [tab] recovered existing tab {t['tabId']} url={t.get('url','')}\n"
                )
                recovered_id = t["tabId"]
                break
        if not recovered_id and b.get("tabs"):
            t = b["tabs"][0]
            sys.stderr.write(f"  [tab] reusing user tab {t['tabId']}\n")
            recovered_id = t["tabId"]
    if not recovered_id:
        return None
    # The recovered tab is the one whose initial POST /tabs hit a 500 from
    # the server's response-side timeout — but the page nav was already
    # in flight server-side and is still loading (title shows
    # "Loading https://...").  DO NOT call /navigate here: per the
    # @askjo/camofox-browser skill, navigate timeout destroys the session,
    # and the second /navigate to the same URL would race with the in-
    # flight first nav.  Just wait for the body to populate (handled by
    # wait_for_body in the caller).
    sys.stderr.write(f"  [tab] using recovered tab {recovered_id} (will wait for body)\n")
    return recovered_id


def close_tab(tab_id, user_id, session_key):
    if not tab_id:
        return
    try:
        _api("DELETE", f"/tabs/{tab_id}?userId={user_id}&sessionKey={session_key}", timeout=10)
    except Exception:
        pass


def wait_for_body(tab_id, user_id, session_key, max_loops=20):
    """Poll document.body.innerText.length until stable for 2 consecutive
    checks (>=100 chars).  Used for both listing and article pages.
    jazztokyo.org often takes >30s to first-load (CF challenge), so default
    max is 40s (20 × 2s) — call sites can raise it for known-slow sites."""
    prev_len = -1
    stable = 0
    for _ in range(max_loops):
        time.sleep(2)
        s, b = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "userId": user_id,
            "sessionKey": session_key,
            "expression": "JSON.stringify({rs: document.readyState, len: document.body ? document.body.innerText.length : 0})"
        })
        if s == 200 and isinstance(b, dict):
            try:
                info = json.loads(b.get("result", "{}"))
            except Exception:
                continue
            cur = info.get("len", 0)
            if cur > 100 and cur == prev_len:
                stable += 1
                if stable >= 2:
                    return True
            else:
                stable = 0
            prev_len = cur
        else:
            # Tab gone (404) — bail early
            return False
    return False


# ── Listing parser ─────────────────────────────────────────────────────

def scrape_listing(page_url, user_id, session_key):
    """Open a FRESH tab on page_url, evaluate link extractor, close it.
    Returns list of {url, title} dicts.
    """
    sys.stderr.write(f"\n=== Listing {page_url} ===\n")
    tid = create_tab_resilient(page_url, user_id, session_key)
    if not tid:
        sys.stderr.write("  [list] failed to get tab — skipping\n")
        return []
    try:
        wait_for_body(tid, user_id, session_key, max_loops=30)
        s, b = _api("POST", f"/tabs/{tid}/evaluate", {
            "userId": user_id,
            "sessionKey": session_key,
            "expression": (
                "(() => { const a = Array.from(document.querySelectorAll('a[href]'));"
                " const out = []; const seen = new Set();"
                " for (const x of a) { let h = x.getAttribute('href') || '';"
                " if (!h || h.startsWith('#')) continue;"
                " const t = (x.innerText || '').trim();"
                " const path = h.startsWith('http') ? new URL(h).pathname : h;"
                " if (!/^\\/[\\w-]+(\\/?[\\w-]+)?\\/post-\\d+\\/?$/.test(path)) continue;"
                " const full = h.startsWith('http') ? h : ('https://jazztokyo.org' + path);"
                " if (seen.has(full)) continue;"
                " seen.add(full);"
                " out.push({h: full, t: t.slice(0, 200)}); } return out; })()"
            ),
        })
        if s != 200 or not isinstance(b, dict):
            sys.stderr.write(f"  [list] eval failed: {s} {str(b)[:100]}\n")
            return []
        result = b.get("result") or []
        links = []
        for item in result:
            h = (item.get("h") or "").strip()
            t = (item.get("t") or "").strip()
            if not h:
                continue
            if "#" in h:
                h = h.split("#", 1)[0]
            if not h.startswith("/") and not h.startswith("http"):
                continue
            path = urllib.parse.urlparse(h).path if h.startswith("http") else h
            if not POST_URL_RE.match(path):
                continue
            url = h if h.startswith("http") else f"{SITE_BASE}{path}"
            links.append({"url": url, "title": t, "path": path})
        sys.stderr.write(f"  [list] found {len(links)} post links\n")
        return links
    finally:
        close_tab(tid, user_id, session_key)


# ── Article parser ────────────────────────────────────────────────────

def parse_article(url, user_id, session_key):
    """Open a FRESH tab on the article URL, parse it, close it.
    Returns dict with title, time_attr, time_text, category, body."""
    sys.stderr.write(f"  [art] {url}\n")
    tid = create_tab_resilient(url, user_id, session_key)
    if not tid:
        return None
    try:
        wait_for_body(tid, user_id, session_key, max_loops=20)
        s, b = _api("POST", f"/tabs/{tid}/evaluate", {
            "userId": user_id,
            "sessionKey": session_key,
            "expression": (
                "(() => { const art = document.querySelector('article') || "
                "document.querySelector('.entry-content') || "
                "document.querySelector('.post') || document.body;"
                " const h1s = Array.from(document.querySelectorAll("
                "'article h1, .entry-title, h1.post-title, h1'));"
                " const t = h1s.length ? h1s.reduce((a,b)=>"
                "(b.innerText||'').length>(a.innerText||'').length?b:a) : null;"
                " const time = document.querySelector('time');"
                " const cat = document.querySelector("
                "'.cat-links a, .category a, .post-categories a');"
                " return { title: t && (t.innerText||'').trim(),"
                " timeAttr: time && time.getAttribute('datetime'),"
                " timeText: time && (time.innerText||'').trim(),"
                " category: cat && (cat.innerText||'').trim(),"
                " body: art ? (art.innerText||'') : '' }; })()"
            ),
        })
        if s != 200 or not isinstance(b, dict):
            sys.stderr.write(f"  [art] eval failed: {s} {str(b)[:100]}\n")
            return None
        res = b.get("result") or {}
        body = res.get("body") or ""
        # Strip noise
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
    finally:
        close_tab(tid, user_id, session_key)


# ── Date parsing ───────────────────────────────────────────────────────

def parse_pub_date(time_attr, time_text, body_text):
    if time_attr:
        m = ISO_DATE_RE.search(time_attr)
        if m:
            try:
                y, mo, d, h, mi, s = map(int, m.groups())
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
    for src in (time_text or "", body_text or "")[:500]:
        m = JP_DATE_RE.search(src)
        if m:
            try:
                y, mo, d = map(int, m.groups())
                return datetime(y, mo, d, 12, 0, 0, tzinfo=timezone.utc), f"{y}-{mo:02d}-{d:02d}"
            except Exception:
                pass
    return None, time_text or ""


# ── Type classification ────────────────────────────────────────────────

def classify_article(url):
    path = urllib.parse.urlparse(url).path
    for p in ("/reviews/cd-dvd-review/", "/reviews/live-report/",
              "/reviews/books/", "/reviews/sound-check/"):
        if p in path:
            return "review"
    return "feature"


# ── Title parsing ──────────────────────────────────────────────────────

TITLE_NUM_RE = re.compile(r"^#\d+\s*")

def split_title(raw_title):
    if not raw_title:
        return "", ""
    t = TITLE_NUM_RE.sub("", raw_title).strip()
    t = re.sub(r"\s+", " ", t)
    m = re.match(r"^([^『』「」]+?)著『([^』]+)』", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.search(r"『([^』]+?)／([^』]+?)』", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    if re.match(r"^[\d/]+\s*[～~\-]", t) or " at " in t:
        return "", t
    m = re.match(r"^(?P<artist>[^『』「」]+?)(?:\s+(?:with|feat|×|x)\s+|\s*[〜~]\s*)(?P<rest>.+)", t)
    if m and len(m.group("artist")) < 60:
        return m.group("artist").strip(), m.group("rest").strip()
    return "", t


# ── Main ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Scrape JazzTokyo (resilient)")
    ap.add_argument("--days", type=float, default=1.5)
    ap.add_argument("--out-dir", type=str,
                    default=os.environ.get("HERMES_KANBAN_WORKSPACE",
                                           "/home/liyifan/music-record/2026/06/2026-06-21"))
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--max-articles", type=int, default=30)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=args.days)

    sys.stderr.write(
        f"JazzTokyo (resilient) — now={now.isoformat()} cutoff={cutoff_date.isoformat()}\n"
    )

    # 1. Collect candidate URLs from up to max_pages listing pages
    candidate_urls = {}
    pages = [HOME_URL, f"{SITE_BASE}/page/2/"][:args.max_pages]
    for n, p in enumerate(pages, 1):
        list_user = f"{USER_ID}_list{n}"
        links = scrape_listing(p, list_user, f"{SESSION_KEY}-list{n}")
        for link in links:
            if link["url"] not in candidate_urls:
                candidate_urls[link["url"]] = link["title"]

    sys.stderr.write(f"\nTotal unique candidates: {len(candidate_urls)}\n")

    # 2. Fetch each article (fresh tab per URL)
    results = []
    kept = 0
    skipped_non_music = 0
    skipped_old = 0
    fetch_errors = 0
    skipped_no_date = 0

    ordered = list(candidate_urls.items())[:args.max_articles]
    for n, (url, list_title) in enumerate(ordered, 1):
        if NON_MUSIC_RE.search(list_title):
            sys.stderr.write(f" [{n}/{len(ordered)}] SKIP non-music (list): {list_title[:60]}\n")
            skipped_non_music += 1
            continue

        art = parse_article(url, f"{USER_ID}_art{n}", f"{SESSION_KEY}-art{n}")
        if art is None:
            sys.stderr.write(f" [{n}/{len(ordered)}] FETCH ERROR: {url}\n")
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
            skipped_no_date += 1
            continue

        if pub_date < cutoff_date:
            sys.stderr.write(f" [{n}/{len(ordered)}] SKIP old (pub={pub_date.date()}): {art['title'][:50]}\n")
            skipped_old += 1
            continue

        type_ = classify_article(url)
        artist, album = split_title(art["title"])
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
        f"non_music={skipped_non_music} old={skipped_old} "
        f"no_date={skipped_no_date} errors={fetch_errors}\n"
    )

    out = {
        "meta": {
            "total": len(results),
            "scraped_at": now.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "site": SITE_ID,
            "hours_scanned": int(args.days * 24),
            "pages_crawled": min(args.max_pages, len(pages)),
            "candidates_checked": len(ordered),
            "in_window_count": kept,
            "non_music_skipped": skipped_non_music,
            "old_skipped": skipped_old,
            "no_date_skipped": skipped_no_date,
            "fetch_errors": fetch_errors,
        },
        "items": results,
    }

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "jazztokyo_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"Wrote {out_path} ({len(results)} items)\n")


if __name__ == "__main__":
    main()
