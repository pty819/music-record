#!/usr/bin/env python3
"""JazzTokyo scraper — jazztokyo.org (monthly magazine, no RSS).

Strategy:
- Homepage is a single static listing of the current issue (26 items via
  `ul.q-block > li` widgets). Each `<li>` carries:
    * `<h3><a href>` — title + post URL pattern `/<cat>/post-NNNNN/`
    * 1st `<p class="entry-meta">` — category tags
    * 2nd `<p class="entry-meta">` — date "M月D日, YYYY年 — author" + 閲覧回数
    * `<p>` excerpt
- Pagination links (`/page/2/`) are decorative — the homepage IS the
  current-issue TOC and there is no chronological archive. The site
  publishes ~monthly; an empty result within a 36h window is expected.
- Japanese date format: "8月15日, 2026年 — 稲岡邦彌" -> year/month/day.
- Camoufox via @askjo/camofox-browser on port 9377 (same gotchas as
  Wild City scraper: tab creation may return delayed-write 500/timeout
  even after the tab exists; always check `GET /tabs` recovery path).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

CAMOFOX_BASE = "http://localhost:9377"
USER_ID = "scraper-jazztokyo"
DAILY_KEY = dt.datetime.utcnow().strftime("daily-%Y-%m-%d")
SESSION_KEY = DAILY_KEY
SITE_ID = "jazztokyo"
SOURCE = "JazzTokyo"
MAX_BODY = 12000
NON_MUSIC = ("(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)")

# Japanese digits (kanji)
KANJI_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


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
    timeout = 15 if method == "POST" and path == "/tabs" else 60
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        return {"_error": body, "_status": e.code}
    except (TimeoutError, urllib.error.URLError):
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
    """Create tab; on timeout or 500, recover via GET /tabs and (if needed) navigate.

    Per the Camoufox skill, when POST /tabs times out, the tab may be created but
    the response write hangs. The recovered tab may also sit at about:blank if
    the original navigation didn't fire — in that case we navigate explicitly.
    """
    res = http("POST", "/tabs", {"userId": USER_ID, "sessionKey": SESSION_KEY, "url": url})
    if isinstance(res, dict) and res.get("tabId"):
        return res
    time.sleep(2.0)
    hostname = url.split("//", 1)[-1].split("/", 1)[0]
    for t in list_tabs():
        if t.get("listItemId") != SESSION_KEY:
            continue
        cur = (t.get("url") or "")
        # Match either navigated URL or about:blank
        if hostname in cur or cur == "about:blank":
            tab_id = t.get("tabId")
            if cur == "about:blank":
                # Navigate explicitly — POST /tabs timed out before navigation fired
                nav = http("POST", f"/tabs/{tab_id}/navigate",
                           {"url": url, "userId": USER_ID, "sessionKey": SESSION_KEY})
                if isinstance(nav, dict) and nav.get("tabId"):
                    return nav
            return t
    delete_session()
    time.sleep(1.0)
    res = http("POST", "/tabs", {"userId": USER_ID, "sessionKey": SESSION_KEY, "url": url})
    if isinstance(res, dict) and res.get("tabId"):
        return res
    return None


def evaluate(tab_id: str, expression: str) -> dict | str:
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


# Homepage extraction — pulls every LI in every `ul.q-block` widget. The
# homepage stacks multiple category widgets (Monthly Editorial, All About
# Jazz, Concerts/Live Shows, etc.) all from the current issue.
HOMEPAGE_EXTRACT_JS = r"""
(() => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll('ul.q-block > li').forEach(li => {
    const h3 = li.querySelector('h3 a');
    if (!h3) return;
    const href = h3.getAttribute('href') || '';
    if (!href || seen.has(href)) return;
    seen.add(href);
    const title = (h3.textContent || '').replace(/\s+/g, ' ').trim();
    // Two .entry-meta blocks: [0]=category tags, [1]=date+author+views
    const metas = li.querySelectorAll('p.entry-meta');
    const dateMeta = metas.length >= 2 ? metas[1] : metas[0];
    const dateLine = dateMeta ? dateMeta.innerText.trim() : '';
    // Excerpt: the first <p> after entry-meta blocks
    const ps = li.querySelectorAll('p');
    let excerpt = '';
    for (const p of ps) {
      if (p.classList.contains('entry-meta')) continue;
      const t = (p.textContent || '').trim();
      if (t.length > 5) { excerpt = t; break; }
    }
    out.push({ href, title, dateLine });
  });
  return out;
})()
"""

# Article body extraction — single post page.
ARTICLE_EXTRACT_JS = r"""
(() => {
  // The <article class="post-NNNN ..."> element wraps the entire post
  const article = document.querySelector('article.post') ||
                  document.querySelector('article[class*="post-"]') ||
                  document.querySelector('article');
  if (!article) return { body: '', dateLine: '', author: '' };
  // Title
  const h1 = article.querySelector('h1');
  const title = h1 ? h1.textContent.trim() : document.title;
  // Date + author from .entry-meta (single-post page has one .entry-meta
  // typically containing "8月15日, 2026年 — 稲岡邦彌")
  const metas = article.querySelectorAll('.entry-meta');
  let dateLine = '';
  let author = '';
  for (const m of metas) {
    const t = (m.textContent || '').trim();
    if (/月.*日.*年/.test(t)) {
      dateLine = t;
      // Author: split on em-dash/—
      const parts = t.split(/[—–-]/);
      if (parts.length >= 2) author = parts[1].trim();
      break;
    }
  }
  // Body: collect all <p> after the date meta block
  const ps = article.querySelectorAll('p, h2, h3, h4, li');
  const bodyParts = [];
  let started = false;
  for (const p of ps) {
    if (p.classList && p.classList.contains('entry-meta')) continue;
    const t = (p.textContent || '').trim();
    if (!t) continue;
    if (!started) {
      // Skip headers / credits before the prose begins
      if (t === title) continue;
      if (/^(CD\/DVD DISKS|NO\.\s*\d+|CD\/DVD|NO\.)/i.test(t)) continue;
      if (/text:/i.test(t) && t.length < 80) continue;
      if (/Tiny Storage Music|¥|税込/.test(t) && t.length < 80) continue;
      if (/^[A-Z][a-z]+:\s*[A-Z]/.test(t) && t.length < 80) continue;
      // Skip tracklist rows (comp./Arr. by patterns + length)
      if (/comp\.|Arr\.|Lyrics|Lyric|作曲|編曲|作詞/.test(t) && t.length < 120) continue;
      if (/^\d+\.\s/.test(t)) continue;
      // Skip musician roster lines (instrument: name, ...)
      if (/^[ア-ンー\s,・]+:[\s\S]{0,200}$/.test(t) && /[：:]/.test(t) && t.length < 200) continue;
      if (/^[A-Za-z][\w\s,.\-:]+,[\s\S]{0,300}$/.test(t) && t.length < 200 && /,/.test(t) && /\b(alto|tenor|bari|trumpet|piano|bass|drums|flute|clarinet|saxophone|sax|trombone|vocal|vo)\b/i.test(t)) continue;
    }
    started = true;
    bodyParts.push(t);
  }
  return { title, dateLine, author, body: bodyParts.join('\n\n') };
})()
"""


def parse_jp_date(s: str) -> dt.date | None:
    """Parse '8月15日, 2026年 — 稲岡邦彌' or '2026年8月15日' -> date."""
    # Form A: 8月15日, 2026年
    m = re.search(r"(\d{1,2})月(\d{1,2})日\s*,\s*(\d{4})\s*年", s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    # Form B: 2026年8月15日
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})月\s*(\d{1,2})日", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    return None


def is_non_music(title: str) -> bool:
    return any(tag in title for tag in NON_MUSIC)


def classify(url: str) -> str:
    if "/reviews/" in url:
        return "review"
    if "/features/" in url or "/feature/" in url:
        return "feature"
    # Editorials / columns / interviews / obits — all type=feature
    return "feature"


def wait_for_body(tab_id: str, max_wait: float = 30.0) -> dict | str | None:
    poll_js = "document.body ? document.body.innerText.length : 0"
    deadline = time.time() + max_wait
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
        page = wait_for_body(tab_id)
        if not page or not isinstance(page, dict):
            return None
        result_obj = page.get("result") if isinstance(page.get("result"), dict) else None
        body = result_obj.get("body") if result_obj else None
        if not body:
            return None
        body = body[:MAX_BODY]
        return {
            "body": body,
            "date_line": result_obj.get("dateLine", ""),
            "author": result_obj.get("author", ""),
        }
    finally:
        close_tab(tab_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, required=True)
    ap.add_argument("--out", default="jazztokyo_reviews.json")
    args = ap.parse_args()

    hours_scanned = int(args.days * 24)
    today_utc = dt.datetime.utcnow().date()
    scraped_at = today_utc.isoformat()
    cutoff = today_utc - dt.timedelta(days=args.days)
    cutoff_str = cutoff.isoformat()

    # 1. Open homepage — current issue TOC.
    feed_tab = create_tab_resilient("https://jazztokyo.org/")
    if not feed_tab:
        print("[jazztokyo] failed to create feed tab", file=sys.stderr)
        return 0
    feed_tab_id = feed_tab["tabId"]

    try:
        # wait for body to settle before extracting
        deadline = time.time() + 30
        last_len = -1
        stable = 0
        while time.time() < deadline:
            r = evaluate(feed_tab_id, "document.body ? document.body.innerText.length : 0")
            if not isinstance(r, dict) or r.get("_error"):
                break
            ln = r.get("result", 0) or 0
            if ln > 1000 and ln == last_len:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
                last_len = ln
            time.sleep(2)
        res = evaluate(feed_tab_id, HOMEPAGE_EXTRACT_JS)
        items_meta = res.get("result", []) if isinstance(res, dict) else []
        if not isinstance(items_meta, list):
            items_meta = []
    finally:
        close_tab(feed_tab_id)

    # 2. Filter
    candidates: list[dict] = []
    seen_urls: set[str] = set()
    for it in items_meta:
        url = it.get("href", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = it.get("title", "").strip()
        d = parse_jp_date(it.get("dateLine", ""))
        if d is None:
            continue
        if d < cutoff:
            continue
        if is_non_music(title):
            continue
        candidates.append({"url": url, "title": title, "date": d.isoformat(),
                            "date_line": it.get("dateLine", "")})

    # 3. Scrape each article (fresh tab per URL)
    items: list[dict] = []
    for c in candidates:
        page = scrape_article(c["url"])
        if not page or not page.get("body"):
            continue
        body = page["body"]
        url = c["url"]
        title = c["title"]
        t = classify(url)
        # For reviews, title format is "#NNNN 『ARTIST／ALBUM』"
        album = title
        artist = ""
        m = re.match(r"^#\d+\s*[『「](.+?)[』」]\s*(.*)$", title)
        if m:
            head = m.group(1)
            tail = m.group(2).strip()
            # head is "ARTIST／ALBUM" or "ARTIST / ALBUM"
            sp = re.split(r"[／/]", head)
            if len(sp) == 2:
                artist = sp[0].strip()
                album = sp[1].strip()
            else:
                album = head
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
            "author": page.get("author", ""),
        })

    out = {
        "meta": {
            "total": len(items),
            "scraped_at": scraped_at,
            "cutoff_date": cutoff_str,
            "hours_scanned": hours_scanned,
            "site": SITE_ID,
        },
        "items": items,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[jazztokyo] wrote {len(items)} items to {args.out} (cutoff={cutoff_str}, "
          f"candidates={len(candidates)}, examined={len(items_meta)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())