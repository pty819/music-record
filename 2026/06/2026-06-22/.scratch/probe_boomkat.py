#!/usr/bin/env python3
"""Diagnostic probe — see what's really being served on the first tab."""
import json, sys, time, urllib.request, urllib.error

CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = "ed63901c7aca4a85bba34ac6ccf6833e"
USER_ID = "scraper_boomkat_probe"
SESSION_KEY = "session_bk_probe"

def _api(method, path, body=None):
    url = f"{CAMOFOX_BASE}{path}"
    if body is None:
        body = {}
    if "userId" not in body and "sessionKey" not in body:
        body = {**body, "userId": USER_ID, "sessionKey": SESSION_KEY}
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CAMOFOX_API_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        sys.stderr.write(f"[E] HTTP {e.code} {method} {path}: {body_text}\n")
        raise

tab = _api("POST", "/tabs", {"url": "https://boomkat.com/new-releases?show=100"})
tab_id = tab.get("tabId")
print(f"tab={tab_id}", flush=True)
if not tab_id:
    print("no tab"); sys.exit(1)

time.sleep(15)

# Capture lots of signals
expr = """
() => ({
    url: location.href,
    title: document.title,
    ready: document.readyState,
    bodyLen: (document.body && document.body.innerText.length) || 0,
    bodyStart: ((document.body && document.body.innerText) || '').substring(0, 600),
    listing: document.querySelectorAll('.listing2__product').length,
    cfMarker: !!document.querySelector('#cf-challenge-running, .cf-browser-verification, #challenge-running'),
    h1: (document.querySelector('h1')||{}).textContent || '',
})
"""
r = _api("POST", f"/tabs/{tab_id}/evaluate", {"expression": expr})
print(json.dumps(r, indent=2, ensure_ascii=False))
try:
    _api("DELETE", f"/tabs/{tab_id}")
except Exception:
    pass
