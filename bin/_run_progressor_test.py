#!/usr/bin/env python3
"""Test Camoufox tab + navigate for ProgressoR."""
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
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:500]}")
    except Exception as e:
        raise RuntimeError(f"{e}")

# 1. List existing tabs, clean up
tabs = _api("GET", "/tabs")
print(f"Existing tabs: {json.dumps(tabs)[:200]}")
existing = tabs.get("tabs", [])
for t in existing:
    tid = t.get("tabId") or t.get("id")
    if tid:
        try:
            _api("DELETE", f"/tabs/{tid}")
            print(f"Deleted tab {tid}")
        except:
            pass
        time.sleep(0.3)

# 2. Create tab WITHOUT url, then navigate
print("\n=== Creating tab (no URL) ===")
tab_resp = _api("POST", "/tabs", {
    "userId": "scraper_progressor",
    "sessionKey": "sess_progressor",
}, timeout=90)
tab_id = tab_resp.get("tabId")
print(f"Tab created: {tab_id}")
if not tab_id:
    print(f"Response: {json.dumps(tab_resp, indent=2)[:300]}")
    sys.exit(1)

# 3. Navigate to HTTP URL
time.sleep(1)
print("\n=== Navigating to HTTP ===")
try:
    nav = _api("POST", f"/tabs/{tab_id}/navigate", {
        "url": "http://www.progressor.net/index.html"
    }, timeout=60)
    print(f"Navigate: {json.dumps(nav)[:300]}")
except Exception as e:
    print(f"Navigate failed: {e}")
    try:
        _api("DELETE", f"/tabs/{tab_id}")
    except:
        pass
    sys.exit(1)

# 4. Get title
time.sleep(2)
print("\n=== Getting title ===")
try:
    title_r = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "() => document.title"
    })
    print(f"Title: {json.dumps(title_r)[:300]}")
except Exception as e:
    print(f"Evaluate: {e}")

# 5. Get body text size
try:
    html_r = _api("POST", f"/tabs/{tab_id}/evaluate", {
        "expression": "() => (document.body.innerText || '').length"
    })
    print(f"Body len: {json.dumps(html_r)[:200]}")
except Exception as e:
    print(f"Body eval: {e}")

# 6. Cleanup
try:
    _api("DELETE", f"/tabs/{tab_id}")
    print("\nCleaned up")
except Exception as e:
    print(f"Cleanup: {e}")
