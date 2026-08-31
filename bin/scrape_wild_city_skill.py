#!/usr/bin/env python3
"""Wild City scraper — thewildcity.com (custom Mamoka CMS, no RSS).

Uses Camoufox via the @askjo/camofox-browser HTTP server. Strategy from
~/.hermes/profiles/scraper/skills/software-development/scraper-wild-city/SKILL.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

CAMOFOX_BASE = "http://localhost:9377"
USER_ID = "scraper-wild-city"
DAILY_KEY = dt.datetime.utcnow().strftime("daily-%Y-%m-%d")
SESSION_KEY = DAILY_KEY
SITE_ID = "wild_city"
SOURCE = "Wild City"
MAX_BODY = 12000
TAG_BUDGET = 30000  # body stable poll budget per article (5s × 6 polls)
NON_MUSIC = ("(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)")


def api_key() -> str:
    return os.environ.get("CAMOFOX_API_KEY", "")


def http(method: str, path: str, body: dict | None = None) -> dict | str:
    req = urllib.request.Request(
        CAMOFOX_BASE + path,
        method=method,
        headers={
            "Authorization": "Bearer " + api_key(),
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    # POST /tabs may hang on the response write even after the tab is created
    # (skill gotcha #1). Tight cap lets us fall back to GET /tabs recovery fast.
    timeout = 15 if method == "POST" and path == "/tabs" else 60
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        return {"_error": body, "_status": e.code}
    except (TimeoutError, urllib.error.URLError):
        # Treat as delayed-write: tab may still exist — caller should check via list_tabs()
        return {"_error": "timeout", "_status": 0}


def list_tabs() -> list[dict]:
    res = http("GET", f"/tabs?userId={USER_ID}&sessionKey={SESSION_KEY}")
    if isinstance(res, dict) and "tabs" in res:
        return res.get("tabs", [])
    if isinstance(res, list):
        return res
    return []


def delete_session() -> None:
    http("DELETE", f"/sessions/{USER_ID}?sessionKey={SESSION_KEY}")


def create_tab_resilient(url: str) -> dict | None:
    """POST /tabs with timeout-tolerant recovery (per skill gotcha #1)."""
    res = http("POST", "/tabs", {"userId": USER_ID, "sessionKey": SESSION_KEY, "url": url})
    if isinstance(res, dict) and res.get("tabId"):
        return res
    # Both delayed-response-timeout AND 500 mean the tab may have been created
    # anyway — always try GET /tabs before giving up.
    time.sleep(2.0)
    for t in list_tabs():
        if t.get("listItemId") == SESSION_KEY and url.split("//", 1)[-1].split("/", 1)[0] in (t.get("url") or ""):
            return t
    # Genuinely dead — wipe session and retry once
    delete_session()
    time.sleep(1.0)
    res = http("POST", "/tabs", {"userId": USER_ID, "sessionKey": SESSION_KEY, "url": url})
    if isinstance(res, dict) and res.get("tabId"):
        return res
    return None


def evaluate(tab_id: str, expression: str) -> dict | str:
    # Camoufox /evaluate needs userId + sessionKey in the body. Without
    # them the server returns 400 {"error":"userId is required"} and
    # every call appears to "fail silently", producing empty results.
    return http(
        "POST",
        f"/tabs/{tab_id}/evaluate",
        {"expression": expression, "userId": USER_ID, "sessionKey": SESSION_KEY},
    )


def close_tab(tab_id: str) -> None:
    try:
        http("DELETE", f"/tabs/{tab_id}")
    except Exception:
        pass


# Sidebar feed extraction — `/features` carries the same `a.box[data-date]` feed as `/home`
SIDEBAR_EXTRACT_JS = """
(() => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll('a.box[data-date]').forEach(a => {
    const href = a.getAttribute('href') || '';
    const date = a.getAttribute('data-date') || '';
    if (!href || !date) return;
    const fullUrl = href.startsWith('http') ? href : ('https://www.thewildcity.com' + (href.startsWith('/') ? '' : '/') + href);
    if (seen.has(fullUrl)) return;
    seen.add(fullUrl);
    // Title: strip leading Review:/Podcast: pills + collapse whitespace
    let title = (a.textContent || '').replace(/\\s+/g, ' ').trim();
    title = title.replace(/^(Review|Podcast|Feature|News|Mix)\\s*:\\s*/i, '');
    out.push({ url: fullUrl, date, title });
  });
  return out;
})()
"""

# Article body extraction
ARTICLE_EXTRACT_JS = """
(() => {
  // Mamoka template: article body lives in .article-body or article > .container
  const candidates = [
    document.querySelector('.article-body'),
    document.querySelector('article .container'),
    document.querySelector('article'),
    document.querySelector('main article'),
    document.querySelector('main'),
  ];
  let node = null;
  for (const c of candidates) { if (c) { node = c; break; } }
  if (!node) node = document.body;
  // Title + lead
  const h1 = document.querySelector('h1');
  const title = h1 ? h1.textContent.trim() : document.title;
  return {
    title,
    body: (node.innerText || '').trim(),
  };
})()
"""


def parse_date_dd_mm_yyyy(s: str) -> dt.date | None:
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s.strip())
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def extract_artist_album(title: str) -> tuple[str, str]:
    """Best-effort split for "Review: ARTIST's 'ALBUM' ..." / "On 'ALBUM', ARTIST ..." titles."""
    t = title.strip()
    # 1. ARTIST's 'ALBUM' ...
    m = re.match(r"^([A-Z][A-Za-z0-9 &.'\\-]+?)'?s\\s*[‘'\"“”]([^‘'\"“”]+)[‘'\"“”]", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # 2. On/Upon 'ALBUM', ARTIST ...
    m = re.match(r"^(?:On|Upon|In)\\s+[‘'\"“”]([^‘'\"“”]+)[‘'\"“”],\\s*([A-Z][A-Za-z0-9 &.'\\-]+)", t)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    # 3. ARTIST — ALBUM (em/en dash)
    m = re.match(r"^([A-Z][A-Za-z0-9 &.'\\-]+?)\\s*[—–-]\\s*(.+)$", t)
    if m and len(m.group(1)) < 40:
        return m.group(1).strip(), m.group(2).strip()
    return "", title


def is_non_music(title: str) -> bool:
    return any(tag in title for tag in NON_MUSIC)


def is_podcast(url: str, title: str) -> bool:
    return "/podcasts/" in url or title.lower().startswith("podcast:")


def classify(title: str, url: str) -> str:
    t = title.lower()
    if t.startswith("review:") or "/reviews/" in url:
        return "review"
    if "/mixes/" in url or t.startswith("mix:"):
        return "feature"  # per skill: /mixes/ → "feature"
    return "feature"


def wait_for_body(tab_id: str, max_wait: float = TAG_BUDGET) -> dict | str | None:
    """Poll body.innerText length until stable for 2 consecutive 2s polls."""
    poll_js = "document.body ? document.body.innerText.length : 0"
    deadline = time.time() + max_wait / 1000.0
    last_len = -1
    stable = 0
    while time.time() < deadline:
        res = evaluate(tab_id, poll_js)
        if not isinstance(res, dict) or res.get("_error"):
            return None
        ln = res.get("result", 0) or 0
        if ln > 100 and ln == last_len:
            stable += 1
            if stable >= 2:
                # Fetch full content
                return evaluate(tab_id, ARTICLE_EXTRACT_JS)
        else:
            stable = 0
            last_len = ln
        time.sleep(2.0)
    return None


def scrape_article(url: str) -> dict | None:
    tab = create_tab_resilient(url)
    if not tab:
        return {"_error": "create_tab_failed"}
    tab_id = tab["tabId"]
    try:
        # create_tab already navigated to url — do NOT call /navigate
        # (skill gotcha #2: navigate timeout destroys session)
        page = wait_for_body(tab_id)
        if not page or not isinstance(page, dict):
            return None
        result_obj = page.get("result") if isinstance(page.get("result"), dict) else None
        body = result_obj.get("body") if result_obj else None
        if not body:
            return None
        body = body[:MAX_BODY]
        return {"body": body}
    finally:
        close_tab(tab_id)


def fetch_feed(tab_id: str) -> list[dict]:
    """Evaluate sidebar feed on /features (carries same data-date feed as /home)."""
    page = wait_for_body(tab_id, max_wait=15000)
    if not page:
        return []
    res = evaluate(tab_id, SIDEBAR_EXTRACT_JS)
    if not isinstance(res, dict) or res.get("_error"):
        return []
    result = res.get("result")
    return result if isinstance(result, list) else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, required=True)
    ap.add_argument("--out", default="wild_city_reviews.json")
    args = ap.parse_args()

    hours_scanned = int(args.days * 24)
    today_utc = dt.datetime.utcnow().date()
    scraped_at = today_utc.isoformat()
    cutoff = today_utc - dt.timedelta(days=args.days)
    cutoff_str = cutoff.isoformat()

    # 1. Open /features (per skill — same sidebar feed, can sit on this tab)
    feed_tab = create_tab_resilient("https://www.thewildcity.com/features")
    if not feed_tab:
        print("[wild_city] failed to create feed tab", file=sys.stderr)
        return 0  # empty result is fine
    feed_tab_id = feed_tab["tabId"]

    try:
        items_meta = fetch_feed(feed_tab_id)
    finally:
        close_tab(feed_tab_id)

    # 2. Filter
    candidates: list[dict] = []
    seen_urls: set[str] = set()
    for it in items_meta:
        url = it["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = it["title"]
        d = parse_date_dd_mm_yyyy(it["date"])
        if d is None:
            continue
        # 36h window
        if d < cutoff:
            continue
        if is_podcast(url, title):
            continue
        if is_non_music(title):
            continue
        candidates.append({"url": url, "title": title, "date": d.isoformat()})

    # 3. Scrape each article (fresh tab per URL — skill gotcha #2)
    items: list[dict] = []
    for c in candidates:
        page = scrape_article(c["url"])
        if not page or not page.get("body"):
            continue
        body = page["body"]
        url = c["url"]
        title = c["title"]
        t = classify(title, url)
        if t == "review":
            artist, album = extract_artist_album(title)
        else:
            artist, album = "", title
        # Excerpt: first ~500 chars of body, stripped
        excerpt = re.sub(r"\s+", " ", body)[:500].strip()
        items.append({
            "album": album,
            "artist": artist,
            "score": None,
            "url": url,
            "source": SOURCE,
            "pub_date": c["date"],
            "tags": "",
            "excerpt": excerpt,
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": t,
        })

    out = {
        "meta": {
            "total": len(items),
            "scraped_at": scraped_at,
            "cutoff_date": cutoff_str,
            "hours_scanned": hours_scanned,
        },
        "items": items,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[wild_city] wrote {len(items)} items to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())