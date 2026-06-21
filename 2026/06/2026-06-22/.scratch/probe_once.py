#!/usr/bin/env python3
"""Single-shot CF check per task body protocol — exactly the JS expression it specifies."""
import json, sys, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:9377"
KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
USER = "probe_cf_one"

def api(method, path, body=None):
    if body is None:
        body = {}
    body.setdefault("userId", USER)
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            txt = r.read().decode()
            return json.loads(txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode()[:300]
        return {"__http_error": e.code, "body": txt}

print("=== Single-shot CF check ===", flush=True)
# 1. Create tab
resp = api("POST", "/tabs", {"sessionKey": "one", "url": "https://boomkat.com/"})
print(f"POST /tabs: {resp}", flush=True)
tab_id = resp.get("tabId") if isinstance(resp, dict) else None

# Per memory: POST /tabs may 500 but tab is created — recover via GET
if not tab_id or resp.get("__http_error"):
    print("[recover via GET /tabs]", flush=True)
    tabs = api("GET", "/tabs")
    if isinstance(tabs, dict):
        for t in tabs.get("tabs", []) or []:
            u = t.get("userId") or t.get("user")
            if u == USER:
                tab_id = t.get("id") or t.get("tabId")
                print(f"recovered tabId={tab_id}", flush=True)
                break

if not tab_id:
    print("FATAL: no tab", flush=True)
    sys.exit(1)

# 2. Wait 15s for CF to auto-solve (per task body)
print("Sleeping 15s...", flush=True)
time.sleep(15)

# 3. The exact CF check JS the task body prescribes
CF_EXPR = "document.title + '|' + document.querySelectorAll('.listing2__product').length"
print(f"Evaluating: {CF_EXPR}", flush=True)
ev = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": CF_EXPR})
print(f"Result: {json.dumps(ev, ensure_ascii=False)}", flush=True)

# Try a few more times in case CF is slowly resolving
for i in range(3):
    time.sleep(5)
    ev = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": CF_EXPR})
    print(f"  +{5*(i+1)}s: {json.dumps(ev, ensure_ascii=False)}", flush=True)
    if isinstance(ev, dict):
        r = ev.get("result")
        if isinstance(r, str) and "|" in r:
            title, _, cnt = r.partition("|")
            if cnt.strip().isdigit() and int(cnt.strip()) > 0:
                print(f"\n*** products>0 at +{5*(i+1)}s: '{r}' ***", flush=True)
                break

# Cleanup
try:
    urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/tabs/{tab_id}", method="DELETE",
        headers={"Authorization": f"Bearer {KEY}"},
        data=b"",  # may need body — DELETE in some servers
    ), timeout=5)
except Exception as e:
    print(f"cleanup warn: {e}", flush=True)
