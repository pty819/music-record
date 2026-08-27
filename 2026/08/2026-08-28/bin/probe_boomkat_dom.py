#!/usr/bin/env python3
"""Probe a Boomkat product page DOM to find the review-text selector.

Usage: probe_boomkat_dom.py <product-url>
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9377"
API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
USER_ID = "scraper_boomkat"
SESSION_KEY = "session_bk_probe"

PROBE_JS = r"""
(() => {
  const out = {};
  out.title = document.title;
  out.h1 = (document.querySelector('h1')||{}).textContent || '';
  const cands = [
    '.product-detail__description', '.product__description', '.product-description',
    '.description', '.product-single__description', '.rte', '.product-review',
    '[itemprop="description"]', '.product-detail__review', '.review',
    '.product-detail__blurb', '.blurb', '.product-info__description',
  ];
  out.selectors = {};
  for (const s of cands) {
    const els = document.querySelectorAll(s);
    if (els.length) {
      out.selectors[s] = Array.from(els).slice(0,2).map(
        e => (e.innerText||'').trim().substring(0, 300));
    }
  }
  // any element whose innerText has a long prose paragraph
  out.longProse = [];
  const all = document.querySelectorAll('div,section,article,p');
  for (const e of all) {
    if (e.children.length > 3) continue;
    const t = (e.innerText||'').trim();
    if (t.length > 200 && t.length < 6000 && !t.includes('Add to crate')) {
      out.longProse.push({
        tag: e.tagName,
        cls: e.className && e.className.toString().substring(0,120),
        len: t.length,
        head: t.substring(0, 200),
      });
    }
  }
  out.longProse = out.longProse.slice(0, 12);
  out.hasReviewMarker = document.body.innerText.includes('Boomkat Product Review');
  return JSON.stringify(out);
})()
"""


def api(method, path, body=None):
    body = dict(body or {})
    body.setdefault("userId", USER_ID)
    body.setdefault("sessionKey", SESSION_KEY)
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code} {method} {path}: {e.read().decode()[:300]}\n")
        raise


def main():
    urls = sys.argv[1:]
    if not urls:
        sys.exit("usage: probe_boomkat_dom.py <url> [url...]")
    tab = api("POST", "/tabs", {"url": "https://boomkat.com/new-releases?show=100"})
    tab_id = tab.get("tabId")
    if not tab_id:
        sys.exit(f"no tabId: {tab}")
    time.sleep(15)
    chk = api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "document.title + '|' + document.querySelectorAll('.listing2__product').length"
    })
    state = str(chk.get("result", ""))
    print("CF check:", state)
    if "Just a moment" in state or state.endswith("|0"):
        api("DELETE", f"/tabs/{tab_id}")
        sys.exit("CF blocked")
    try:
        for u in urls:
            api("POST", f"/tabs/{tab_id}/navigate", {"url": u})
            time.sleep(2)
            r = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": PROBE_JS})
            raw = r.get("result")
            print("=" * 70)
            print(u)
            print(json.dumps(json.loads(raw) if isinstance(raw, str) else raw,
                             indent=2, ensure_ascii=False)[:4000])
    finally:
        try:
            api("DELETE", f"/tabs/{tab_id}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
