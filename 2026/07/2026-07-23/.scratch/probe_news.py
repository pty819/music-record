#!/usr/bin/env python3
"""Probe: how many sidebar/anchor items appear on /news and ?offset=10 now?"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

API = "http://127.0.0.1:9377"
KEY = os.environ.get("CAMOFOX_API_KEY", "ed63901c7aca4a85bba34ac6ccf6833e")


def api(method, path, body=None, timeout=90):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Authorization": f"Bearer {KEY}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return None, str(e)


def probe(label, url, user_id):
    s, b = api("POST", "/tabs", {
        "userId": user_id, "sessionKey": "probe", "url": url
    }, timeout=120)
    if s != 200 or not isinstance(b, dict) or not b.get("tabId"):
        print(f"[{label}] create_tab failed: status={s} body={str(b)[:200]}")
        return
    tab_id = b["tabId"]
    print(f"[{label}] tab={tab_id}")
    try:
        # Wait for readiness.
        for _ in range(15):
            time.sleep(2)
            s2, b2 = api("POST", f"/tabs/{tab_id}/evaluate", {
                "userId": user_id, "expression": "document.readyState"
            }, timeout=15)
            if s2 == 200 and isinstance(b2, dict) and b2.get("result") == "complete":
                break
        # Now extract listing info.
        s3, b3 = api("POST", f"/tabs/{tab_id}/evaluate", {
            "userId": user_id,
            "expression": "(() => ({ sidebar: document.querySelectorAll('a[data-date]').length, anchors: document.querySelectorAll('a[href*=\"/news/\"]').length, first5: Array.from(document.querySelectorAll('a[data-date]')).slice(0,5).map(a => (a.getAttribute('data-date') || '') + ' | ' + (a.textContent || '').trim().slice(0,60)), has_articles: !!document.querySelector('article'), h_titles: Array.from(document.querySelectorAll('h1,h2,h3')).slice(0,3).map(h => h.textContent.trim().slice(0,80)) }))()",
        }, timeout=30)
        print(f"[{label}] evaluate status={s3} result={b3.get('result') if isinstance(b3, dict) else b3}")
    finally:
        api("DELETE", f"/tabs/{tab_id}?userId={user_id}", timeout=10)
        api("DELETE", f"/sessions/{user_id}?userId={user_id}", timeout=10)


probe("page1", "https://www.thewildcity.com/news", f"scraper_probe_1_{int(time.time())}")
probe("page2", "https://www.thewildcity.com/news?offset=10", f"scraper_probe_2_{int(time.time())}")
