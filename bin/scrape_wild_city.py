#!/usr/bin/env python3
"""Tolerant Wild City scraper — handles /tabs 500 by re-listing and reusing tabs."""
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
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "")
TARGET_URL = "https://www.thewildcity.com/features"

SITE_ID = "wild_city"
SOURCE = "Wild City"
TAGS = "indie,electronic,india"
USER_ID = "scraper_wild_city"
SESSION_KEY = "session_wc"
NON_MUSIC_RE = re.compile(r"\((BLU-RAY|UHD|VOD|DVD)\)", re.IGNORECASE)


def _api(method, path, body=None, timeout=180):
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if CAMOFOX_API_KEY:
        req.add_header("Authorization", f"Bearer {CAMOFOX_API_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return None, str(e)


def create_tab_resilient(url, user_id, session_key, max_wait_s=60):
    """POST /tabs but tolerate 500 — the tab may have been created.
    Returns tab_id or None."""
    status, body = _api("POST", "/tabs", {
        "userId": user_id, "sessionKey": session_key, "url": url
    }, timeout=max_wait_s)
    if status == 200 and isinstance(body, dict) and body.get("tabId"):
        sys.stderr.write(f"  tab created OK ({body['tabId']})\n")
        return body["tabId"]
    # Otherwise, look for an existing tab for this user
    sys.stderr.write(f"  POST /tabs returned {status}: {str(body)[:200]}\n")
    sys.stderr.write("  checking for existing tab...\n")
    s, b = _api("GET", f"/tabs?userId={user_id}")
    if s == 200 and isinstance(b, dict):
        for t in b.get("tabs", []):
            if t.get("listItemId") == session_key:
                sys.stderr.write(f"  recovered existing tab {t['tabId']} (url={t.get('url','')})\n")
                return t["tabId"]
        # No tab in this session — take any tab for the user
        if b.get("tabs"):
            t = b["tabs"][0]
            sys.stderr.write(f"  reusing user tab {t['tabId']}\n")
            return t["tabId"]
    return None


def close_tab(tab_id, user_id):
    if not tab_id:
        return
    try:
        _api("DELETE", f"/tabs/{tab_id}?userId={user_id}", timeout=10)
    except Exception:
        pass


def evaluate_js(tab_id, expression, user_id=None):
    uid = user_id or USER_ID
    status, body = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "userId": uid, "expression": expression
    })
    if status == 200 and isinstance(body, dict):
        return body.get("result")
    return None


def evaluate_js_safe(tab_id, user_id, expression):
    """evaluate_js with explicit user_id (no default)."""
    status, body = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "userId": user_id, "expression": expression
    })
    if status == 200 and isinstance(body, dict):
        return body.get("result")
    return None


def parse_date_dd_mm_yyyy(text):
    text = (text or "").strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text)
    if not m:
        return ""
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
    except ValueError:
        return ""


def extract_artist_album(title):
    """Pull artist/album from 'Review: ...' titles.

    Examples that should work:
      "Review: Gorkhali Takeover — A Compilation Honouring South Asian Diaspora" -> ("", "Gorkhali Takeover ...")
      "Review: Anoushka Shankar — Chapter II: How Dark It Is Before The Dawn" -> ("Anoushka Shankar", "Chapter II: ...")
      "Review: Arooj Aftab — Night Reign" -> ("Arooj Aftab", "Night Reign")
    """
    text = re.sub(r"^review:\s*", "", title.strip(), flags=re.IGNORECASE)
    if "—" in text:
        parts = [p.strip() for p in text.split("—", 1)]
        return parts[0], parts[1]
    if " - " in text:
        parts = [p.strip() for p in text.split(" - ", 1)]
        return parts[0], parts[1]
    return "", text


def fetch_body(tab_id):
    js = "document.querySelector('article')?.innerText?.slice(0, 12000) || document.body?.innerText?.slice(0, 12000) || ''"
    return str(evaluate_js(tab_id, js) or "").strip()


EXTRACT_FEED_JS = """
const items = [];
const seen = new Set();
const els = document.querySelectorAll('a.box[data-date]');
for (const el of els) {
    const href = el.getAttribute('href') || '';
    if (!href || seen.has(href)) continue;
    seen.add(href);
    const date = el.getAttribute('data-date') || '';
    const text = (el.innerText || '').trim();
    const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
    let title = lines[0] || '';
    if (lines.length > 1 && /^(review|podcast|feature|tracklist|interview|news)$/i.test(lines[0])) {
        title = lines[1] || title;
    }
    items.push({
        url: href.startsWith('http') ? href : 'https://www.thewildcity.com' + href,
        date: date,
        title: title,
    });
}
items;
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=float, default=1.5)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--out", type=str,
                        default="/home/liyifan/music-record/2026/06/2026-06-20/wild_city_reviews.json")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    if args.date:
        cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        cutoff_date = today - timedelta(days=args.days)

    sys.stderr.write(f"Wild City — Today: {today}, Cutoff: {cutoff_date}\n")

    # Phase 1: collect feed
    tab_id = create_tab_resilient(TARGET_URL, USER_ID, SESSION_KEY)
    if not tab_id:
        result = {"meta": {"total": 0, "scraped_at": today.isoformat(),
                            "cutoff_date": cutoff_date.isoformat(),
                            "hours_scanned": int(args.days * 24)},
                  "items": []}
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.stderr.write("FAILED to get a tab — wrote empty result\n")
        sys.exit(1)

    feed_raw = evaluate_js(tab_id, EXTRACT_FEED_JS) or []
    sys.stderr.write(f"  found {len(feed_raw)} feed items\n")

    # Phase 2: filter
    candidates = []
    skipped_old = skipped_podcast = skipped_non_music = 0
    for item in feed_raw:
        url = item.get("url", "")
        date_str = item.get("date", "")
        title = item.get("title", "")
        if not (url and date_str and title):
            continue
        if "/podcasts/" in url.lower() or url.lower().endswith("podcasts"):
            skipped_podcast += 1
            continue
        if NON_MUSIC_RE.search(title):
            skipped_non_music += 1
            continue
        pub_date = parse_date_dd_mm_yyyy(date_str)
        if not pub_date:
            continue
        try:
            item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if item_date < cutoff_date:
            skipped_old += 1
            continue
        candidates.append({"url": url, "date": date_str,
                           "pub_date": pub_date, "title": title})

    sys.stderr.write(
        f"  candidates: {len(candidates)} "
        f"(skip old={skipped_old} podcast={skipped_podcast} non_music={skipped_non_music})\n"
    )

    # Phase 3: fetch bodies — each URL gets its own tab.
    # Reusing the same tab via /navigate destroys it on timeout,
    # so we create fresh tabs (tolerating the 500) and recover.
    max_items = min(args.max_items, 20)
    items = []
    body_user = f"scraper_wc_body_{int(time.time())}"
    for idx, c in enumerate(candidates[:max_items]):
        url = c["url"]
        title = c["title"]
        pub_date = c["pub_date"]
        is_review = title.lower().startswith("review:")
        item_type = "review" if is_review else "feature"
        score = None
        if is_review:
            artist, album = extract_artist_album(title)
        else:
            artist, album = "", title

        sys.stderr.write(f"  [{idx+1}] fetching body for {url[:80]}...\n")
        body_tab = create_tab_resilient(
            url, body_user, f"body_{idx}", max_wait_s=60
        )
        body = ""
        if body_tab:
            # Wait for body to stabilize (page may stay 'loading' due to embeds)
            prev_len = -1
            stable_count = 0
            for k in range(15):
                time.sleep(2)
                try:
                    rs = evaluate_js_safe(body_tab, body_user,
                        "JSON.stringify({rs: document.readyState, len: document.body ? document.body.innerText.length : 0})"
                    )
                    if rs and isinstance(rs, str):
                        info = json.loads(rs)
                        cur_len = info.get("len", 0)
                        if cur_len > 100 and cur_len == prev_len:
                            stable_count += 1
                            if stable_count >= 2:
                                break
                        else:
                            stable_count = 0
                        prev_len = cur_len
                except Exception:
                    pass
            time.sleep(1)
            js = "document.querySelector('article')?.innerText?.slice(0, 12000) || document.body?.innerText?.slice(0, 12000) || ''"
            body = str(evaluate_js_safe(body_tab, body_user, js) or "").strip()
            close_tab(body_tab, body_user)

        excerpt = (body[:500] if body else title)
        items.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": TAGS,
            "excerpt": excerpt,
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success" if body else "empty_body",
            "type": item_type,
        })
        sys.stderr.write(f"  [{idx+1}] {item_type} {url} ({len(body)} chars)\n")

    items.sort(key=lambda it: it.get("pub_date", "") or "0000-00-00", reverse=True)

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": today.isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
            "hours_scanned": int(args.days * 24),
        },
        "items": items,
    }

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    close_tab(tab_id, USER_ID)
    sys.stderr.write(f"\nTotal: {len(items)} items — wrote {args.out}\n")


if __name__ == "__main__":
    main()