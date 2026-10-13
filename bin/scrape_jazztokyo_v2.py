#!/usr/bin/env python3
"""
scrape_jazztokyo_v2.py — JazzTokyo scraper, two-phase to fit 7-min budget:

Phase 1 (date scout): for each candidate URL, open a fresh tab, read ONLY the
<time datetime> attribute, close. ~2s per article × 40 = ~80s. Surfaces
which URLs are inside the 36h window without paying full body-fetch cost on
the ~33 stale ones.

Phase 2 (body fetch): only for in-window URLs, open a fresh tab, full eval.
~3-5s per article.

Mirrors scrape_jazztokyo_resilient.py but split into two passes so a mid-run
CF/tab death doesn't waste work on articles we'd skip anyway.
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

CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "")
SITE_BASE = "https://jazztokyo.org"
HOME_URL = f"{SITE_BASE}/"

SITE_ID = "jazztokyo"
SOURCE = "JazzTokyo"
TAGS_DEFAULT = "jazz,free improvisation,free jazz,japanese jazz"
USER_ID = "scraper_jazztokyo_v2"
SESSION_KEY = f"daily-{datetime.now(timezone.utc).date().isoformat()}-jazztokyo-v2"

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|UHD|VOD|DVD|Blu-ray|4K)\)", re.I)
JP_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})")
POST_URL_RE = re.compile(r"^/(?:[a-z-]+/)*post-(\d+)/?$")


def _api(method, path, body=None, timeout=60):
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"} if data else {}
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


def create_tab(url, user_id, session_key, max_wait_s=60):
    status, body = _api("POST", "/tabs", {
        "userId": user_id, "sessionKey": session_key, "url": url
    }, timeout=max_wait_s)
    if status == 200 and isinstance(body, dict) and body.get("tabId"):
        return body["tabId"]
    sys.stderr.write(f"  [tab {session_key[-12:]}] POST /tabs returned {status}: {str(body)[:120]}\n")
    return None


def close_tab(tab_id, user_id, session_key):
    if not tab_id:
        return
    try:
        _api("DELETE", f"/tabs/{tab_id}?userId={user_id}&sessionKey={session_key}", timeout=10)
    except Exception:
        pass


def wait_for_body(tab_id, user_id, session_key, max_loops=15):
    prev_len = -1
    stable = 0
    for _ in range(max_loops):
        time.sleep(2)
        s, b = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "userId": user_id, "sessionKey": session_key,
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
            return False
    return False


def scrape_listing(page_url, user_id, session_key):
    sys.stderr.write(f"\n=== Listing {page_url} ===\n")
    tid = create_tab(page_url, user_id, session_key)
    if not tid:
        return []
    try:
        if not wait_for_body(tid, user_id, session_key, max_loops=20):
            sys.stderr.write("  [list] body never settled\n")
            return []
        s, b = _api("POST", f"/tabs/{tid}/evaluate", {
            "userId": user_id, "sessionKey": session_key,
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


def date_scout(url, user_id, session_key):
    """Open article, read just the <time datetime> attribute, close.
    Returns (datetime_utc_or_None, raw_attr_str)."""
    tid = create_tab(url, user_id, session_key, max_wait_s=30)
    if not tid:
        return None, None
    try:
        if not wait_for_body(tid, user_id, session_key, max_loops=10):
            return None, None
        s, b = _api("POST", f"/tabs/{tid}/evaluate", {
            "userId": user_id, "sessionKey": session_key,
            "expression": (
                "(() => { const t = document.querySelector('time'); "
                "const h1s = Array.from(document.querySelectorAll('h1, .entry-title')); "
                "const title = h1s.length ? (h1s.reduce((a,b)=>(b.innerText||'').length>(a.innerText||'').length?b:a).innerText||'').trim() : ''; "
                "return JSON.stringify({dt: t && t.getAttribute('datetime'), text: t && (t.innerText||'').trim(), title}); })()"
            ),
        })
        if s != 200 or not isinstance(b, dict):
            return None, None
        try:
            info = json.loads(b.get("result", "{}"))
        except Exception:
            return None, None
        dt_attr = info.get("dt") or ""
        title = info.get("title") or ""
        # Parse the datetime attr
        m = ISO_DATE_RE.search(dt_attr)
        if m:
            try:
                y, mo, d, h, mi, s2 = map(int, m.groups())
                tz_match = re.search(r"([+-])(\d{2}):(\d{2})$", dt_attr)
                if tz_match:
                    sign = 1 if tz_match.group(1) == "+" else -1
                    offset_minutes = sign * (int(tz_match.group(2)) * 60 + int(tz_match.group(3)))
                    tz_off = timezone(timedelta(minutes=offset_minutes))
                else:
                    tz_off = timezone.utc
                return datetime(y, mo, d, h, mi, s2, tzinfo=tz_off), title
            except Exception:
                pass
        # Fallback to JP date
        text = info.get("text") or ""
        m = JP_DATE_RE.search(text)
        if m:
            try:
                y, mo, d = map(int, m.groups())
                return datetime(y, mo, d, 12, 0, 0, tzinfo=timezone.utc), title
            except Exception:
                pass
        return None, title
    finally:
        close_tab(tid, user_id, session_key)


def parse_article_full(url, list_title, user_id, session_key):
    """Open article, full eval for body. Returns item dict or None."""
    tid = create_tab(url, user_id, session_key, max_wait_s=30)
    if not tid:
        return None
    try:
        if not wait_for_body(tid, user_id, session_key, max_loops=15):
            sys.stderr.write(f"  [full] body never settled for {url}\n")
            return None
        s, b = _api("POST", f"/tabs/{tid}/evaluate", {
            "userId": user_id, "sessionKey": session_key,
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
            return None
        res = b.get("result") or {}
        body = res.get("body") or ""
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


def classify_article(url):
    path = urllib.parse.urlparse(url).path
    for p in ("/reviews/cd-dvd-review/", "/reviews/live-report/",
              "/reviews/books/", "/reviews/sound-check/"):
        if p in path:
            return "review"
    return "feature"


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


def main():
    ap = argparse.ArgumentParser(description="Scrape JazzTokyo (v2: scout-then-fetch)")
    ap.add_argument("--days", type=float, default=1.5)
    ap.add_argument("--out-dir", type=str,
                    default=os.environ.get("HERMES_KANBAN_WORKSPACE",
                                           "/home/liyifan/music-record/2026/06/2026-06-21"))
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--max-articles", type=int, default=40)
    ap.add_argument("--budget-s", type=int, default=300,
                    help="Soft wall-clock budget for the whole run (default 300s = 5min)")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=args.days)
    run_start = time.time()

    sys.stderr.write(
        f"JazzTokyo v2 — now={now.isoformat()} cutoff={cutoff_date.isoformat()} "
        f"budget={args.budget_s}s\n"
    )

    # ── Phase 0: collect candidate URLs from listing pages ──
    candidate_urls = {}
    pages = [HOME_URL, f"{SITE_BASE}/page/2/"][:args.max_pages]
    for n, p in enumerate(pages, 1):
        list_user = f"{USER_ID}_list{n}"
        list_key = f"{SESSION_KEY}-list{n}"
        links = scrape_listing(p, list_user, list_key)
        for link in links:
            if link["url"] not in candidate_urls:
                candidate_urls[link["url"]] = link["title"]
        if time.time() - run_start > args.budget_s * 0.3:
            sys.stderr.write("  [phase0] budget guard: stopping listing crawl\n")
            break

    sys.stderr.write(f"\nTotal unique candidates: {len(candidate_urls)}\n")

    # ── Phase 1: date scout each article ──
    in_window = []  # list of (url, list_title, pub_date, scouted_title)
    pre_non_music = 0
    no_date_count = 0
    date_err = 0

    ordered = list(candidate_urls.items())[:args.max_articles]
    sys.stderr.write(f"\n=== Phase 1: date scout ({len(ordered)} articles) ===\n")
    for n, (url, list_title) in enumerate(ordered, 1):
        if time.time() - run_start > args.budget_s * 0.5:
            sys.stderr.write(f"  [scout] budget guard at {n}/{len(ordered)}, stopping scout\n")
            break
        if NON_MUSIC_RE.search(list_title):
            pre_non_music += 1
            continue
        scout_user = f"{USER_ID}_scout{n}"
        scout_key = f"{SESSION_KEY}-scout{n}"
        pub_date, scouted_title = date_scout(url, scout_user, scout_key)
        if pub_date is None:
            if scouted_title:
                no_date_count += 1
                sys.stderr.write(f" [{n}/{len(ordered)}] scout no-date: {url} :: {scouted_title[:50]}\n")
            else:
                date_err += 1
                sys.stderr.write(f" [{n}/{len(ordered)}] scout ERR: {url}\n")
            continue
        if pub_date < cutoff_date:
            sys.stderr.write(f" [{n}/{len(ordered)}] scout old ({pub_date.date()}): {url}\n")
            continue
        sys.stderr.write(f" [{n}/{len(ordered)}] scout IN-WINDOW ({pub_date.date()}): {url}\n")
        in_window.append((url, list_title, pub_date, scouted_title))

    sys.stderr.write(
        f"\nPhase 1 done: in_window={len(in_window)} pre_non_music={pre_non_music} "
        f"no_date={no_date_count} err={date_err}\n"
    )

    # ── Phase 2: full body fetch for in-window items only ──
    sys.stderr.write(f"\n=== Phase 2: body fetch ({len(in_window)} in-window) ===\n")
    results = []
    for n, (url, list_title, pub_date, scouted_title) in enumerate(in_window, 1):
        if time.time() - run_start > args.budget_s * 0.9:
            sys.stderr.write(f"  [body] budget guard at {n}/{len(in_window)}, stopping\n")
            break
        body_user = f"{USER_ID}_body{n}"
        body_key = f"{SESSION_KEY}-body{n}"
        art = parse_article_full(url, list_title, body_user, body_key)
        if art is None:
            sys.stderr.write(f" [{n}/{len(in_window)}] body FETCH ERR: {url}\n")
            continue

        full_text = (art["title"] + "\n" + art["body"])
        if NON_MUSIC_RE.search(full_text[:1500]):
            sys.stderr.write(f" [{n}/{len(in_window)}] body SKIP non-music: {url}\n")
            continue

        type_ = classify_article(url)
        artist, album = split_title(art["title"] or scouted_title)
        if not album:
            album = art["title"] or scouted_title or list_title

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
        sys.stderr.write(f" [{n}/{len(in_window)}] KEPT ({type_}, {pub_date.date()}): {(art['title'] or scouted_title)[:50]}\n")

    out = {
        "meta": {
            "total": len(results),
            "scraped_at": now.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "site": SITE_ID,
            "hours_scanned": int(args.days * 24),
            "pages_crawled": min(args.max_pages, len(pages)),
            "candidates_checked": len(ordered),
            "in_window_count": len(results),
            "scout_pre_non_music": pre_non_music,
            "scout_no_date": no_date_count,
            "scout_errors": date_err,
        },
        "items": results,
    }

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "jazztokyo_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"\nWrote {out_path} ({len(results)} items, {time.time()-run_start:.1f}s)\n")


if __name__ == "__main__":
    main()
