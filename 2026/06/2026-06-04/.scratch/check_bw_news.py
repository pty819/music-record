#!/usr/bin/env python3
"""Check Bandwagon Asia News and Features categories."""
import json, urllib.request, sys, time
from datetime import datetime, timezone, timedelta

CAMOFOX = "http://127.0.0.1:9377"
CUTOFF = datetime.now(timezone.utc) - timedelta(hours=36)

def req(method, path, body=None):
    url = f"{CAMOFOX}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())

def get_articles(url):
    tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":url})
    tid = tab.get("tabId","")
    time.sleep(2)
    js = """() => {
        const items = [];
        const blocks = document.querySelectorAll('.article-block');
        blocks.forEach(b => {
            const link = b.querySelector('.article-block__title');
            const title = link ? link.textContent.trim() : '';
            const url = link ? link.href : '';
            if (title && url) items.push({title, url});
        });
        return JSON.stringify(items);
    }"""
    resp = req("POST", f"/tabs/{tid}/evaluate", {"expression": js})
    arts = json.loads(resp.get("result","[]"))
    req("DELETE", f"/tabs/{tid}")
    return arts

print("=== News ===")
news = get_articles("https://www.bandwagon.asia/categories/news")
print(f"Found {len(news)} articles")
for n in news[:20]:
    print(f"  {n['title'][:70]} -> {n['url']}")

print("\n=== News page 2 ===")
news2 = get_articles("https://www.bandwagon.asia/categories/news?page=2")
print(f"Found {len(news2)} articles")
for n in news2[:10]:
    print(f"  {n['title'][:70]} -> {n['url']}")

print("\n=== Features ===")
feats = get_articles("https://www.bandwagon.asia/categories/feature")
print(f"Found {len(feats)} articles")
for f in feats[:20]:
    print(f"  {f['title'][:70]} -> {f['url']}")

all_to_check = (news + news2 + feats)[:10]
print(f"\n=== Checking dates on {len(all_to_check)} articles (cutoff={CUTOFF.isoformat()}) ===")
for a in all_to_check:
    tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":a['url']})
    tid = tab.get("tabId","")
    time.sleep(2)
    resp = req("POST", f"/tabs/{tid}/evaluate", {"expression":"""() => {
        const timeEl = document.querySelector('time');
        let dt = '';
        if (timeEl) dt = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
        const h1 = document.querySelector('h1');
        const title = h1 ? h1.textContent.trim() : '';
        return JSON.stringify({date: dt, title});
    }"""})
    d = json.loads(resp.get("result","{}"))
    dt_str = d.get('date','?')
    within = False
    if dt_str:
        try:
            pub = datetime.fromisoformat(dt_str.replace('Z','+00:00'))
            within = pub >= CUTOFF
        except: pass
    print(f"  within={within} date={dt_str[:30]} | {a['title'][:50]}")
    req("DELETE", f"/tabs/{tid}")
    time.sleep(1)
