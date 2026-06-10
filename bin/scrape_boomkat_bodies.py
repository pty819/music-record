#!/usr/bin/env python3
"""
Pass-2: Visit each Boomkat product URL to fetch full body text.
Splits work into batches of BATCH_SIZE to avoid Camoufox memory pressure
(~42 visits causes crash on ARM64).
"""
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

CAMOFOX_BASE = "http://127.0.0.1:9377"
BATCH_SIZE = 25  # Stay well under the 42-visit crash threshold

GET_PRODUCT_BODY_JS = """
() => {
    const bodyText = document.body.innerText;
    const reviewMarker = 'Boomkat Product Review:';
    const tracksMarker = 'Tracks for';

    let body = '';
    const reviewIdx = bodyText.indexOf(reviewMarker);
    if (reviewIdx >= 0) {
        const startIdx = reviewIdx + reviewMarker.length;
        let endIdx = bodyText.indexOf(tracksMarker, startIdx);
        if (endIdx < 0 || endIdx - startIdx > 8000) {
            for (const marker of ['Tracks', 'Tracklist', 'Format', 'Related Products', 'You might also like']) {
                const idx = bodyText.indexOf(marker, startIdx);
                if (idx > 0 && idx - startIdx < 8000) {
                    endIdx = idx;
                    break;
                }
            }
        }
        if (endIdx < 0 || endIdx > bodyText.length) {
            endIdx = startIdx + 5000;
        }
        body = bodyText.substring(startIdx, endIdx).trim();
    }

    if (!body) {
        const contentEl = document.querySelector('.content') || document.body;
        body = contentEl.textContent.trim();
    }

    const h1 = document.querySelector('h1');
    const title = h1 ? h1.textContent.trim() : '';
    return { body: body.substring(0, 10000), title: title };
}
"""


def _api(method, path, body=None):
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {body_text}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/boomkat_pass1.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/boomkat_pass2.json"
    start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    end = int(sys.argv[4]) if len(sys.argv) > 4 else None

    data = json.load(open(in_path))
    items = data["items"]
    if end is None:
        end = len(items)
    print(f"Processing items [{start}:{end}] of {len(items)} total", file=sys.stderr)

    tab_id = None
    processed = 0
    succeeded = 0
    failed = 0
    batch_count = 0

    for idx in range(start, end):
        item = items[idx]
        # Open fresh tab at start of each batch
        if processed % BATCH_SIZE == 0:
            if tab_id:
                try:
                    _api("DELETE", f"/tabs/{tab_id}")
                except Exception:
                    pass
            tab_resp = _api("POST", "/tabs", {
                "userId": "scraper_boomkat",
                "sessionKey": f"session_bk_{idx}",
                "url": item["url"],
            })
            tab_id = tab_resp.get("tabId")
            if not tab_id:
                sys.stderr.write(f"ERROR: Failed to create tab at idx {idx}\n")
                item["crawl_status"] = "partial"
                failed += 1
                processed += 1
                continue
            time.sleep(2)  # Initial page load
            batch_count += 1

        url = item["url"]
        try:
            _api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
            time.sleep(1.5)

            resp = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": GET_PRODUCT_BODY_JS})
            detail = resp.get("result") or {}
            body = (detail.get("body") or "").strip()

            if body:
                item["body"] = body
                if not item.get("excerpt") or len(item.get("excerpt", "")) < 50:
                    item["excerpt"] = body[:500]
                item["crawl_status"] = "success"
                succeeded += 1
            else:
                item["crawl_status"] = "partial"
                failed += 1

            sys.stderr.write(f"  [{idx+1}/{end}] {item['artist'] or '?'} : {item['album'][:40]}... body={len(body)}c\n")
        except Exception as e:
            sys.stderr.write(f"  [{idx+1}/{end}] ERROR {item['artist']}: {e}\n")
            item["crawl_status"] = "partial"
            failed += 1
            # Browser might have crashed — try to reopen
            try:
                if tab_id:
                    _api("DELETE", f"/tabs/{tab_id}")
            except Exception:
                pass
            tab_id = None

        processed += 1

    # Close final tab
    if tab_id:
        try:
            _api("DELETE", f"/tabs/{tab_id}")
        except Exception:
            pass

    # Save results
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Processed: {processed}, Succeeded: {succeeded}, Failed: {failed}, Batches: {batch_count}", file=sys.stderr)
    print(f"Saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
