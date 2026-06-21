#!/usr/bin/env python3
"""Open Boomkat listing, wait, then probe DOM state."""
import json, sys, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:9377"
KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
USER = "probe_cf_diag"


def api(method, path, body=None):
    if body is None:
        body = {}
    body.setdefault("userId", USER)
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        print(f"[E] HTTP {e.code} {method} {path}: {body_text}", file=sys.stderr)
        raise


print("Creating tab...", flush=True)
tab_id = None
try:
    tab = api("POST", "/tabs", {"sessionKey": "diag", "url": "https://boomkat.com/new-releases?show=100"})
    tab_id = tab["tabId"]
    print(f"tabId={tab_id} (direct)", flush=True)
except urllib.error.HTTPError:
    print("[RECOVER] POST /tabs failed, retrieving via GET /tabs...", flush=True)
    tabs = api("GET", "/tabs")
    mine = [t for t in (tabs.get("tabs") or []) if (t.get("userId") or t.get("user")) == USER]
    if mine:
        tab_id = mine[0].get("id") or mine[0].get("tabId")
        print(f"tabId={tab_id} (recovered)", flush=True)
if not tab_id:
    print("FATAL: no tab available", file=sys.stderr)
    sys.exit(1)

PROBE = """
() => ({
    url: location.href,
    title: document.title,
    ready: document.readyState,
    products: document.querySelectorAll('.listing2__product').length,
    bodyStart: (document.body ? document.body.innerText : '').substring(0, 400),
    htmlStart: (document.documentElement ? document.documentElement.outerHTML : '').substring(0, 400),
})
"""

prev = 0
for delay in (10, 25, 45):
    print(f"\n--- Waiting until t={delay}s, then probing ---", flush=True)
    time.sleep(delay - prev)
    prev = delay
    # Multiple probes in case complex expressions error on CF page
    for label, expr in [
        ("title-count", "document.title + '|' + document.querySelectorAll('.listing2__product').length"),
        ("just-title", "document.title"),
        ("full", """() => ({
    url: location.href,
    title: document.title,
    ready: document.readyState,
    products: document.querySelectorAll('.listing2__product').length,
    bodyStart: (document.body ? document.body.innerText : '').substring(0, 400),
})"""),
    ]:
        r = api("POST", f"/tabs/{tab_id}/evaluate", {"expression": expr})
        print(f"  [{label}] {json.dumps(r, ensure_ascii=False)}", flush=True)
    result = r.get("result") if isinstance(r, dict) else None
    if isinstance(result, dict) and result.get("products", 0) > 0:
        print(f"\n*** Products found at t={delay}s! ***", flush=True)
        break
    if isinstance(result, str) and "|" in result:
        title, _, cnt = result.partition("|")
        if cnt.strip().isdigit() and int(cnt.strip()) > 0:
            print(f"\n*** Products found at t={delay}s (via title-count probe)! ***", flush=True)
            break

try:
    api("DELETE", f"/tabs/{tab_id}")
except Exception:
    pass
