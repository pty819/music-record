#!/usr/bin/env python3
"""Test Camoufox tab creation with HTTP URL for ProgressoR."""
import json
import urllib.request
import urllib.error
import sys
import time

CAMOFOX_BASE = "http://127.0.0.1:9377"

def _api(method, path, body=None, timeout=60):
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")[:500]
        print(f"HTTP {e.code}: {err_body}", file=sys.stderr)
        raise RuntimeError(f"HTTP {e.code}: {err_body}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise

# Try creating tab with URL (same as scraper does)
print("=== Create tab with HTTP URL ===")
try:
    tab_resp = _api("POST", "/tabs", {
        "userId": "scraper_progressor",
        "sessionKey": "sess_progressor",
        "url": "http://www.progressor.net/index.html",
    }, timeout=90)
    tab_id = tab_resp.get("tabId")
    print(f"Tab: {tab_id}")
    if not tab_id:
        print(f"Full response: {json.dumps(tab_resp, indent=2)[:500]}")
        sys.exit(1)
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Get body length
time.sleep(3)
print("\n=== Evaluate ===")
try:
    resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "() => ({title: document.title, bodyLen: (document.body.innerText || '').length, url: document.location.href})"
    })
    print(f"Result: {json.dumps(resp, indent=2)[:500]}")
except Exception as e:
    print(f"FAILED: {e}")

# Navigate to history_short
print("\n=== Navigate to history_short ===")
try:
    nav = _api("POST", f"/tabs/{tab_id}/navigate", {
        "url": "http://www.progressor.net/history_short.html"
    }, timeout=60)
    print(f"Navigate: {json.dumps(nav)[:200]}")
    time.sleep(2)
    resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "() => ({title: document.title, bodyLen: (document.body.innerText || '').length})"
    })
    print(f"After nav: {json.dumps(resp, indent=2)[:300]}")
except Exception as e:
    print(f"FAILED: {e}")

# Cleanup
try:
    _api("DELETE", f"/tabs/{tab_id}")
    print("\nCleaned up")
except:
    pass
