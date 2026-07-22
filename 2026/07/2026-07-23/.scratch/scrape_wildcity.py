#!/usr/bin/env python3
"""2026-07-23 runner: scrape Wild City for the music-recs pipeline.

Spec contract (from kanban task t_a18d1ec6):
  - 36h cutoff (--days 1.5)
  - Max 2 listing pages from /news (no /news?offset=10 page 2 unless it returns)
  - Extract sidebar (with data-date) + anchor items, dedupe by id
  - Visit each article via fresh tab (one tab per article avoids /navigate 500)
  - Skip non-music (BLU-RAY/UHD/VOD/DVD), skip podcasts
  - Skip articles whose date (sidebar or body first <p>) < cutoff
  - type: review iff title starts with "Review:", else feature
  - Output JSON {meta, items} to wild_city_reviews.json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "ed63901c7aca4a85bba34ac6ccf6833e")
SITE_URL = "https://www.thewildcity.com"
LISTING_URLS = [f"{SITE_URL}/news", f"{SITE_URL}/news?offset=10"]

SITE_ID = "wild_city"
SOURCE = "Wild City"
TAGS_DEFAULT = "south asian,alternative,electronic"
NON_MUSIC_RE = re.compile(r'\((BLU-RAY|UHD|VOD|DVD)\)', re.IGNORECASE)

BJT = timezone(timedelta(hours=8))


def _api(method, path, body=None, timeout=60):
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Authorization": f"Bearer {CAMOFOX_API_KEY}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        return e.code, body_text
    except Exception as e:
        return None, str(e)


def create_tab(user_id, session_key, url, max_wait_s=120):
    """Create a tab; on 500/timeout, recover by listing tabs and reusing."""
    status, body = _api(
        "POST", "/tabs",
        {"userId": user_id, "sessionKey": session_key, "url": url},
        timeout=max_wait_s,
    )
    if status == 200 and isinstance(body, dict) and body.get("tabId"):
        return body["tabId"], None
    # Tab may have been created despite the 500; list and reuse.
    s, b = _api("GET", f"/tabs?userId={user_id}", timeout=10)
    if s == 200 and isinstance(b, dict):
        for t in b.get("tabs", []) or []:
            if t.get("listItemId") == session_key:
                return t["tabId"], "recovered"
    return None, f"status={status} body={str(body)[:200]}"


def close_tab(tab_id, user_id):
    if not tab_id:
        return
    try:
        _api("DELETE", f"/tabs/{tab_id}?userId={user_id}", timeout=10)
    except Exception:
        pass
    try:
        _api("DELETE", f"/sessions/{user_id}?userId={user_id}", timeout=10)
    except Exception:
        pass


EXTRACT_LISTING_JS = r"""
(() => {
  const NEWS_PATH = /\/news\/(\d+)-/;
  const MIXES_PATH = /\/mixes\/(\d+)-/;
  const FEATURES_PATH = /\/features\/(\d+)-/;
  const PODCASTS_PATH = /\/podcasts\/(\d+)-/;
  const SECTION_FOR = (url) => {
    if (NEWS_PATH.test(url)) return 'news';
    if (MIXES_PATH.test(url)) return 'mixes';
    if (FEATURES_PATH.test(url)) return 'features';
    if (PODCASTS_PATH.test(url)) return 'podcasts';
    return null;
  };
  const NUM_FOR = (url) => {
    let m = url.match(NEWS_PATH) || url.match(MIXES_PATH) || url.match(FEATURES_PATH) || url.match(PODCASTS_PATH);
    return m ? parseInt(m[1]) : null;
  };
  const sidebar = [];
  document.querySelectorAll('a[data-date]').forEach(a => {
    const href = a.href || '';
    const section = SECTION_FOR(href);
    if (!section) return;
    const id = NUM_FOR(href);
    if (!id) return;
    const date = (a.getAttribute('data-date') || '').trim();
    const text = a.textContent.trim().split(/[\r\n]+/)[0].trim().slice(0, 250);
    sidebar.push({ id, url: href, title: text, date, section });
  });
  const anchors = [];
  const seen = new Set();
  document.querySelectorAll('a').forEach(a => {
    const href = a.href || '';
    const section = SECTION_FOR(href);
    if (!section) return;
    const id = NUM_FOR(href);
    if (!id || seen.has(id)) return;
    seen.add(id);
    const text = a.textContent.trim().split(/[\r\n]+/)[0].trim().slice(0, 250);
    anchors.push({ id, url: href, title: text, section });
  });
  return { sidebar, anchors, location: location.href };
})()
"""


GET_ARTICLE_BODY_JS = r"""
(() => {
  const article = document.querySelector('article.layout-article');
  if (!article) return { found: false };
  const rows = article.querySelectorAll('.row');
  if (!rows.length) return { found: false };
  const divs = rows[0].querySelectorAll('.span-w-12');
  if (divs.length < 2) return { found: false };
  const div2 = divs[1];
  const paras = Array.from(div2.querySelectorAll('p'));
  const dateText = paras.length ? paras[0].textContent.trim() : '';
  const bodyParas = paras.slice(1).map(p => p.textContent.trim()).filter(t => t.length > 0);
  const body = bodyParas.join('\n\n');
  const h1 = document.querySelector('h1');
  const title = h1 ? h1.textContent.trim() : '';
  return { found: true, dateText: dateText, body: body, title: title };
})()
"""


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_dd_mm_yyyy(s):
    if not s:
        return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s.strip())
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
    except ValueError:
        return None


def parse_text_date(text):
    """Parse dates like '23 July, 2026' / 'July 23, 2026' / '23 July 2026'."""
    text = (text or "").strip()
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text)
    # Try 'DD Month, YYYY'
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})", text)
    if m:
        d, mon, y = int(m.group(1)), MONTHS.get(m.group(2).lower()), int(m.group(3))
        if mon and d:
            try:
                return datetime(y, mon, d).date().isoformat()
            except ValueError:
                pass
    # Try 'Month DD, YYYY'
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2})\s*,?\s+(\d{4})", text)
    if m:
        mon, d, y = MONTHS.get(m.group(1).lower()), int(m.group(2)), int(m.group(3))
        if mon and d:
            try:
                return datetime(y, mon, d).date().isoformat()
            except ValueError:
                pass
    return None


def collect_listing(page_url, user_id, session_key):
    """Open a fresh tab on the listing page, return (sidebar, anchors, error)."""
    tab_id, err = create_tab(user_id, session_key, page_url, max_wait_s=90)
    if not tab_id:
        return [], [], f"create_tab failed: {err}"
    try:
        # Wait until at least one data-date anchor exists (proves JS hydrated).
        for _ in range(20):
            time.sleep(1.5)
            s, b = _api(
                "POST", f"/tabs/{tab_id}/evaluate",
                {
                    "userId": user_id,
                    "expression": "document.querySelectorAll('a[data-date]').length",
                },
                timeout=15,
            )
            count = 0
            if s == 200 and isinstance(b, dict):
                try:
                    count = int(b.get("result") or 0)
                except Exception:
                    count = 0
            if count >= 1:
                time.sleep(1)  # small grace for anchors to render too
                break
        # Extract listing.
        s, b = _api(
            "POST", f"/tabs/{tab_id}/evaluate",
            {"userId": user_id, "expression": EXTRACT_LISTING_JS},
            timeout=30,
        )
        if s != 200 or not isinstance(b, dict):
            return [], [], f"evaluate failed: status={s} body={str(b)[:200]}"
        payload = b.get("result") or {}
        return payload.get("sidebar") or [], payload.get("anchors") or [], None
    finally:
        close_tab(tab_id, user_id)


def fetch_article(url, user_id, session_key):
    """Open a fresh tab on an article, return (title, body, dateText) or err string."""
    tab_id, err = create_tab(user_id, session_key, url, max_wait_s=90)
    if not tab_id:
        return None, None, None, f"create_tab failed: {err}"
    try:
        # Wait for the body to stabilize.
        stable = 0
        prev_len = -1
        for _ in range(15):
            time.sleep(2)
            s, b = _api(
                "POST", f"/tabs/{tab_id}/evaluate",
                {
                    "userId": user_id,
                    "expression": "JSON.stringify({rs: document.readyState, len: document.querySelector('article') ? (document.querySelector('article').innerText || '').length : 0})",
                },
                timeout=15,
            )
            if s == 200 and isinstance(b, dict):
                rs = b.get("result")
                try:
                    info = json.loads(rs) if isinstance(rs, str) else {}
                except Exception:
                    info = {}
                cur_len = info.get("len", 0)
                if cur_len > 100 and cur_len == prev_len:
                    stable += 1
                    if stable >= 2:
                        break
                else:
                    stable = 0
                prev_len = cur_len
        s, b = _api(
            "POST", f"/tabs/{tab_id}/evaluate",
            {"userId": user_id, "expression": GET_ARTICLE_BODY_JS},
            timeout=30,
        )
        if s == 200 and isinstance(b, dict):
            payload = b.get("result") or {}
            if payload.get("found"):
                return (
                    payload.get("title") or "",
                    payload.get("body") or "",
                    payload.get("dateText") or "",
                    None,
                )
        # Fallback: try plain article.innerText.
        s2, b2 = _api(
            "POST", f"/tabs/{tab_id}/evaluate",
            {
                "userId": user_id,
                "expression": "(() => { const a = document.querySelector('article'); const txt = a ? a.innerText : (document.body ? document.body.innerText : ''); const paras = (a ? a.querySelectorAll('p') : document.querySelectorAll('p')); let dateText = ''; for (const p of paras) { const t = (p.textContent || '').trim(); if (/\d/.test(t) && /\\d{4}/.test(t) && t.length < 200) { dateText = t; break; } } return JSON.stringify({title: (document.querySelector('h1') || {}).textContent || '', body: (txt || '').slice(0, 12000), dateText}); })()",
            },
            timeout=30,
        )
        if s2 == 200 and isinstance(b2, dict):
            try:
                payload = json.loads(b2.get("result") or "{}")
            except Exception:
                payload = {}
            return (
                payload.get("title") or "",
                payload.get("body") or "",
                payload.get("dateText") or "",
                None,
            )
        return None, None, None, "evaluate failed"
    finally:
        close_tab(tab_id, user_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=1.5)
    ap.add_argument("--out", default="/home/liyifan/music-record/2026/07/2026-07-23/wild_city_reviews.json")
    ap.add_argument("--max-articles", type=int, default=30)
    args = ap.parse_args()

    now_bjt = datetime.now(BJT)
    today = now_bjt.date()
    cutoff_date = today - timedelta(days=args.days)
    now_utc = datetime.now(timezone.utc)

    sys.stderr.write(f"Wild City scraper - today (BJT)={today} cutoff={cutoff_date}\n")

    # Phase 1: collect from listing pages.
    seen_ids = set()
    all_articles_raw = []  # {id, url, title, date, source_sidebar}
    for page_idx, listing in enumerate(LISTING_URLS):
        user_id = f"scraper_wc_list_{int(time.time())}_{page_idx}"
        session_key = f"list_{page_idx}"
        sys.stderr.write(f"\n=== Listing page {page_idx + 1}: {listing} ===\n")
        sidebar, anchors, err = collect_listing(listing, user_id, session_key)
        if err:
            sys.stderr.write(f"  ERROR collecting page: {err}\n")
        sys.stderr.write(f"  sidebar={len(sidebar)} anchors={len(anchors)}\n")

        # Index sidebar by id for date lookup.
        sidebar_by_id = {item["id"]: item for item in sidebar}

        for item in sidebar:
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            if "/podcasts/" in item["url"]:
                continue
            if NON_MUSIC_RE.search(item.get("title", "")):
                continue
            date_iso = parse_dd_mm_yyyy(item.get("date", ""))
            if date_iso and datetime.strptime(date_iso, "%Y-%m-%d").date() < cutoff_date:
                continue
            all_articles_raw.append({
                "id": item["id"],
                "url": item["url"],
                "title": item["title"],
                "date": date_iso,
                "source_list": "sidebar",
            })

        for item in anchors:
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            if "/podcasts/" in item["url"]:
                continue
            if NON_MUSIC_RE.search(item.get("title", "")):
                continue
            all_articles_raw.append({
                "id": item["id"],
                "url": item["url"],
                "title": item["title"],
                "date": None,
                "source_list": "anchor",
            })

    sys.stderr.write(f"\nTotal unique article candidates (after date/podcast/non-music filters): {len(all_articles_raw)}\n")

    # Phase 2: per-article body fetches.
    items = []
    cutoff_str = cutoff_date.isoformat()
    art_count = min(len(all_articles_raw), args.max_articles)
    for i, art in enumerate(all_articles_raw[:art_count]):
        url = art["url"]
        known_date = art.get("date")
        sys.stderr.write(f"\n[{i + 1}/{art_count}] id={art['id']} {url} (known_date={known_date})\n")

        # Type: review iff title starts with "Review:".
        title_lower = art.get("title", "").lower()
        item_type = "review" if (
            title_lower.startswith("review:") or " review:" in title_lower[:20]
        ) else "feature"

        # Skip already-out-of-window via sidebar date.
        if known_date:
            try:
                if datetime.strptime(known_date, "%Y-%m-%d").date() < cutoff_date:
                    sys.stderr.write(f"  SKIP (sidebar date {known_date} before cutoff {cutoff_date})\n")
                    continue
            except ValueError:
                pass

        user_id = f"scraper_wc_art_{int(time.time())}_{i}"
        session_key = f"art_{i}"
        title, body, date_text, err = fetch_article(url, user_id, session_key)
        if err:
            sys.stderr.write(f"  ERROR: {err}\n")
            continue

        if not body:
            sys.stderr.write(f"  WARN: empty body, keeping listing title\n")
            body = ""
            title = title or art["title"]
        else:
            title = (title or art["title"]).strip()
            body = body.strip()

        # Date: prefer sidebar, then body dateText.
        pub_date = known_date
        if not pub_date and date_text:
            parsed = parse_text_date(date_text) or parse_dd_mm_yyyy(date_text)
            if parsed:
                pub_date = parsed
                try:
                    if datetime.strptime(pub_date, "%Y-%m-%d").date() < cutoff_date:
                        sys.stderr.write(f"  SKIP (body date {pub_date} before cutoff {cutoff_date})\n")
                        continue
                except ValueError:
                    pass
        if not pub_date:
            pub_date = today.isoformat()

        excerpt = body[:500] if body else ""
        item = {
            "album": title or "Unknown",
            "artist": "Wild City Editors",
            "score": None,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": TAGS_DEFAULT,
            "excerpt": excerpt,
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success" if body else "partial",
            "type": item_type,
        }
        items.append(item)
        sys.stderr.write(f"  OK {item_type} - {title[:60]!r} ({pub_date}, {len(body)} chars)\n")

    # Phase 3: write out.
    result = {
        "meta": {
            "total": len(items),
            "scraped_at": now_utc.isoformat(),
            "cutoff_date": cutoff_str,
            "hours_scanned": int(args.days * 24),
        },
        "items": items,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"\nWrote {len(items)} items to {args.out}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
