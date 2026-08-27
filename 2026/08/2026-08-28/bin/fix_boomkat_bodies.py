#!/usr/bin/env python3
"""fix_boomkat_bodies.py — re-extract body/excerpt for Boomkat items whose
body is cart-widget junk rather than editorial prose.

Root cause: scrape_boomkat.py's extractor looks for the literal marker
'Boomkat Product Review:' in document.body.innerText and, when absent,
falls back to `.content`/`document.body` textContent — which on a Boomkat
product page is the price/format/add-to-crate widget. Many singles and
reissues simply have no editorial review, so those items ended up with
several hundred chars of chrome as their "body".

This script uses the precise DOM node instead:
  .product-review-mobile  (or #product-review / .tabs-content review pane)
and reports has_review=False when the page genuinely carries no review,
writing the release metadata line as the body instead of cart junk.

Usage: fix_boomkat_bodies.py <path-to-boomkat_reviews.json>
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9377"
API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
USER_ID = "scraper_boomkat"
SESSION_KEY = "session_bk_fix"

EXTRACT_JS = r"""
(() => {
  const clean = t => (t || '')
    .replace(/\r/g, '')
    .split('\n').map(l => l.trim()).filter(Boolean).join('\n')
    .trim();

  // 1) The dedicated review node. Boomkat renders the editorial copy twice
  //    (desktop tab pane + mobile block); the mobile one is the cleanest.
  let review = '';
  const revEl = document.querySelector('.product-review-mobile')
             || document.querySelector('#product-review')
             || document.querySelector('.product-review');
  if (revEl) review = clean(revEl.innerText);
  // Fallback: the desktop tab pane carries the same copy and is not collapsed.
  if (!review || review.length < 60) {
    const tab = document.querySelector('.tabs-content');
    if (tab) {
      const t = clean(tab.innerText);
      const i = t.indexOf('Boomkat Product Review:');
      if (i >= 0) review = t.slice(i);
    }
  }
  if (review.startsWith('Boomkat Product Review:')) {
    review = review.slice('Boomkat Product Review:'.length).trim();
  }
  // The review node is present even on releases with no editorial copy; it
  // then holds nothing but the collapse toggle ('View more' / 'View less').
  // Drop those UI lines, and treat what is left as a review only if it is
  // actually prose-sized.
  review = review.split('\n')
    .filter(l => !/^(view (more|less)|read more|show more)$/i.test(l.trim()))
    .join('\n')
    .trim();
  if (review.length < 60) review = '';

  // Trim anything that follows the editorial copy (tracklist / cart chrome).
  if (review) {
    for (const stop of ['Tracks for', 'Tracklist', 'View less',
                        'Add to crate', 'More from', 'You might also like']) {
      const si = review.indexOf(stop);
      if (si > 60) review = review.slice(0, si).trim();
    }
  }

  // 2) Release metadata line, used as body when there is no review at all.
  let meta = '';
  const keeper = document.querySelector('.detail__keeper');
  if (keeper) {
    const line = clean(keeper.innerText)
      .split('\n')
      .find(l => /Cat No:/i.test(l));
    if (line) meta = line;
  }

  const h1 = document.querySelector('h1');
  const h2 = document.querySelector('.detail__keeper h2, h2');
  return JSON.stringify({
    review: review.substring(0, 20000),
    meta: meta,
    artist: h1 ? clean(h1.innerText) : '',
    album: h2 ? clean(h2.innerText) : '',
    has_review: review.length > 0,
    title: document.title,
  });
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


def is_junk(body: str) -> bool:
    """True when body has no real prose paragraph or is mostly widget chrome."""
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    if not lines:
        return True
    prose = [ln for ln in lines if len(ln) > 120]
    chrome = sum(1 for ln in lines
                 if len(ln) < 30 or ln.startswith("£") or "Add to crate" in ln)
    return (not prose) or (chrome / len(lines) > 0.75)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: fix_boomkat_bodies.py <boomkat_reviews.json>")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    items = data["items"]

    targets = [(n, it) for n, it in enumerate(items) if is_junk(it.get("body"))]
    sys.stderr.write(f"items={len(items)} junk={len(targets)}\n")
    if not targets:
        sys.stderr.write("nothing to do\n")
        return

    tab = api("POST", "/tabs", {"url": "https://boomkat.com/new-releases?show=100"})
    tab_id = tab.get("tabId")
    if not tab_id:
        sys.exit(f"no tabId: {tab}")
    time.sleep(15)
    chk = api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "document.title + '|' + document.querySelectorAll('.listing2__product').length"
    })
    state = str(chk.get("result", ""))
    sys.stderr.write(f"CF check: {state}\n")
    if "Just a moment" in state or state.endswith("|0"):
        api("DELETE", f"/tabs/{tab_id}")
        sys.exit(2)

    fixed = no_review = failed = 0
    try:
        for k, (n, it) in enumerate(targets, 1):
            url = it["url"]
            sys.stderr.write(f"[{k}/{len(targets)}] idx={n} {it.get('album','')[:40]}\n")
            try:
                api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                time.sleep(1.5)
                r = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": EXTRACT_JS})
                raw = r.get("result")
                d = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception as e:
                sys.stderr.write(f"   ERROR {e}\n")
                failed += 1
                if "410" in str(e) or "browser_restarted" in str(e):
                    try:
                        api("DELETE", f"/tabs/{tab_id}")
                    except Exception:
                        pass
                    tab = api("POST", "/tabs",
                              {"url": "https://boomkat.com/new-releases?show=100"})
                    tab_id = tab.get("tabId")
                    time.sleep(15)
                continue

            if d.get("has_review"):
                body = d["review"]
                it["body"] = body
                it["excerpt"] = body[:500]
                it["crawl_status"] = "success"
                it["has_review"] = True
                fixed += 1
                sys.stderr.write(f"   review {len(body)} chars\n")
            else:
                meta_line = d.get("meta") or ""
                it["body"] = meta_line
                it["excerpt"] = meta_line[:500]
                it["crawl_status"] = "success"
                it["has_review"] = False
                no_review += 1
                sys.stderr.write(f"   no editorial review; meta='{meta_line[:80]}'\n")

        sys.stderr.write(
            f"\nfixed={fixed} no_review={no_review} failed={failed}\n")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        sys.stderr.write(f"wrote {path}\n")
    finally:
        try:
            api("DELETE", f"/tabs/{tab_id}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
