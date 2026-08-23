#!/usr/bin/env python3
"""Quick check: see the newest pub_dates on the JazzTokyo listing pages
without iterating through every article. Confirms whether 2026-08-15 is
genuinely the most recent post (no in-window items) or just a stale
view."""
import json
import time
import urllib.request
import urllib.error
import sys

API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
BASE = "http://127.0.0.1:9377"
SITE = "https://jazztokyo.org"
USER = "jt_quickcheck"
SESS = "jtcheck-once"


def api(method, path, body=None, timeout=120):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return None, str(e)


def get_articles_from_listing(listing_url, tag):
    """Open one fresh tab on the listing page, extract (url, datetime) pairs
    from each article card."""
    s, b = api("POST", "/tabs", {"userId": USER, "sessionKey": SESS, "url": listing_url})
    print(f"[{tag}] create tab: {s} {str(b)[:200]}")
    if s != 200 or not isinstance(b, dict):
        return []
    tid = b.get("tabId")
    # Wait for body
    for i in range(40):
        time.sleep(2)
        s2, b2 = api("POST", f"/tabs/{tid}/evaluate", {
            "userId": USER, "sessionKey": SESS,
            "expression": "JSON.stringify({len: document.body ? document.body.innerText.length : 0})",
        })
        if s2 == 200 and isinstance(b2, dict):
            try:
                info = json.loads(b2.get("result", "{}"))
            except Exception:
                continue
            if info.get("len", 0) > 1000:
                print(f"[{tag}] body ready ({info['len']} chars) at {i*2}s")
                break
    else:
        print(f"[{tag}] body never settled")
    # Extract article dates
    s2, b2 = api("POST", f"/tabs/{tid}/evaluate", {
        "userId": USER, "sessionKey": SESS,
        "expression": (
            "(() => {"
            "  const arts = document.querySelectorAll('article');"
            "  const out = [];"
            "  for (const a of arts) {"
            "    const h = a.querySelector('a[href*=\"/post-\"]');"
            "    const time = a.querySelector('time');"
            "    if (!h) continue;"
            "    const href = h.getAttribute('href');"
            "    const dt = time ? time.getAttribute('datetime') : '';"
            "    const txt = (time ? time.innerText : '') || '';"
            "    const title = (h.innerText || '').trim().slice(0, 80);"
            "    out.push({href, dt, txt, title});"
            "  }"
            "  return out;"
            "})()"
        ),
    })
    api("DELETE", f"/tabs/{tid}?userId={USER}&sessionKey={SESS}")
    if s2 == 200 and isinstance(b2, dict):
        return b2.get("result") or []
    print(f"[{tag}] eval failed: {s2} {str(b2)[:200]}")
    return []


# Just check page 1 (newest)
rows1 = get_articles_from_listing(f"{SITE}/", "home")
print(f"\n--- Homepage (page 1) — {len(rows1)} articles ---")
for r in rows1[:30]:
    print(f"  {r.get('dt', ''):35} {r.get('txt', ''):25} | {r.get('title', '')[:60]}")

# Compare to a fresh curl-like check via Camoufox (also verify freshness via
# HTTP Last-Modified)
s, b = api("GET", f"/fetch?url={SITE}/")
print(f"\n[http check] {SITE}/ -> {s} {str(b)[:200]}")
