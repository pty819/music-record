#!/usr/bin/env python3
"""boomkat_recover_bodies.py — recovery script: visit each missing-body URL
with a fresh Camoufox tab, write body back into boomkat_reviews.json.

Used when scrape_boomkat.py tab dies mid-visit-loop and leaves some items
without a body. Reads boomkat_reviews.json, finds items with empty body,
visits each URL in a fresh tab (with 15s CF wait), patches the file.
"""
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

CAMOFOX_BASE = "http://127.0.0.1:9377"
API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
USER_ID = "scraper_boomkat"
SESSION_KEY = "session_bk_recover"

GET_PRODUCT_BODY_JS = """
(() => {
  const bodyText = document.body.innerText;
  const marker = 'Boomkat Product Review:';
  const tracksMarker = 'Tracks for';
  let body = '';
  const idx = bodyText.indexOf(marker);
  if (idx >= 0) {
    let endIdx = bodyText.indexOf(tracksMarker, idx + marker.length);
    if (endIdx < 0 || endIdx - idx > 8000) {
      for (const m of ['Tracks', 'Tracklist', 'Format', 'Related Products', 'You might also like']) {
        const mi = bodyText.indexOf(m, idx + marker.length);
        if (mi > 0 && mi - idx < 8000) { endIdx = mi; break; }
      }
    }
    if (endIdx < 0 || endIdx > bodyText.length) endIdx = idx + marker.length + 5000;
    body = bodyText.substring(idx + marker.length, endIdx).trim();
  }
  if (!body) {
    const ce = document.querySelector('.content') || document.body;
    body = ce.textContent.trim();
  }
  const h1 = document.querySelector('h1');
  return JSON.stringify({ body: body.substring(0, 10000), title: h1 ? h1.textContent.trim() : '' });
})()
"""

def api(method, path, body=None):
    url = f"{CAMOFOX_BASE}{path}"
    if body is None:
        body = {}
    if "userId" not in body:
        body = {**body, "userId": USER_ID, "sessionKey": SESSION_KEY}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        sys.stderr.write(f"[ERROR] HTTP {e.code} {method} {path}: {body_text}\n")
        raise

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: boomkat_recover_bodies.py <path-to-boomkat_reviews.json>\n")
        sys.exit(1)
    path = Path(sys.argv[1])
    with path.open() as f:
        data = json.load(f)

    items = data["items"]
    missing = [(i, it) for i, it in enumerate(items) if not (it.get("body") or "").strip()]
    sys.stderr.write(f"Total items: {len(items)}; missing bodies: {len(missing)}\n")
    if not missing:
        sys.stderr.write("Nothing to do.\n")
        return

    # Fresh tab + 15s CF wait. Land on /new-releases so the .listing2__product
    # check is meaningful (homepage has 0 products, which would false-positive).
    sys.stderr.write("Creating fresh tab and waiting 15s for CF...\n")
    tab_resp = api("POST", "/tabs", {"url": "https://boomkat.com/new-releases?show=100"})
    tab_id = tab_resp.get("tabId")
    if not tab_id:
        sys.stderr.write("ERROR: Failed to create tab\n")
        sys.exit(1)
    time.sleep(15)
    cf_check = api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "document.title + '|' + document.querySelectorAll('.listing2__product').length"
    })
    cf_state = str(cf_check.get("result", ""))
    sys.stderr.write(f"CF check after 15s: {cf_state}\n")
    if "Just a moment" in cf_state or cf_state.endswith("|0"):
        sys.stderr.write("CF still active or empty list — aborting recovery\n")
        api("DELETE", f"/tabs/{tab_id}")
        sys.exit(2)

    try:
        recovered = 0
        for k, (idx, it) in enumerate(missing):
            url = it["url"]
            sys.stderr.write(f"  [{k+1}/{len(missing)}] idx={idx} {it.get('artist','?')} : {it.get('album','')[:40]}...\n")
            try:
                api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
                time.sleep(1.5)
                resp = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": GET_PRODUCT_BODY_JS})
                raw = resp.get("result")
                detail = json.loads(raw) if isinstance(raw, str) else (raw or {})
                body = (detail.get("body") or "").strip()
                if body:
                    it["body"] = body
                    if not it.get("excerpt"):
                        it["excerpt"] = body[:500]
                    recovered += 1
                    sys.stderr.write(f"    body: {len(body)} chars\n")
                else:
                    sys.stderr.write(f"    body: EMPTY\n")
            except Exception as e:
                sys.stderr.write(f"    ERROR: {e}\n")
                # tab died — try to recreate
                if "410" in str(e) or "browser_restarted" in str(e):
                    sys.stderr.write("    tab died — recreating\n")
                    try:
                        api("DELETE", f"/tabs/{tab_id}")
                    except Exception:
                        pass
                    tab_resp = api("POST", "/tabs", {"url": "https://boomkat.com/"})
                    tab_id = tab_resp.get("tabId")
                    if tab_id:
                        time.sleep(15)
                it["crawl_status"] = "partial"
        sys.stderr.write(f"\nRecovered {recovered}/{len(missing)} bodies\n")

        with path.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        sys.stderr.write(f"Wrote updated {path}\n")
    finally:
        try:
            api("DELETE", f"/tabs/{tab_id}")
        except Exception:
            pass

if __name__ == "__main__":
    main()
