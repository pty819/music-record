#!/usr/bin/env python3
"""Check dates on Listen category articles and also news category."""
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

# Get listen articles
tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":"https://www.bandwagon.asia/categories/listen"})
tid = tab.get("tabId","")
time.sleep(3)

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
listen_articles = json.loads(resp.get("result","[]"))
req("DELETE", f"/tabs/{tid}")

print(f"=== Listen: {len(listen_articles)} articles ===")
for a in listen_articles:
    print(f"  {a['title'][:60]} -> {a['url']}")

# Check page 2
print("\n--- Checking page 2 of Listen ---")
tab2 = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":"https://www.bandwagon.asia/categories/listen?page=2"})
tid2 = tab2.get("tabId","")
time.sleep(2)
resp2 = req("POST", f"/tabs/{tid2}/evaluate", {"expression": js})
arts2 = json.loads(resp2.get("result","[]"))
req("DELETE", f"/tabs/{tid2}")
print(f"Page 2: {len(arts2)} articles")
for a in arts2[:10]:
    print(f"  {a['title'][:60]} -> {a['url']}")

# Check dates on each listen article
print(f"\n=== Checking dates (cutoff = {CUTOFF.isoformat()}) ===")
all_articles = listen_articles + arts2

for i, a in enumerate(all_articles):
    tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":a['url']})
    tid = tab.get("tabId","")
    time.sleep(2)
    
    js_data = """() => {
        const timeEl = document.querySelector('time');
        let dt = '';
        if (timeEl) dt = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
        const h1 = document.querySelector('h1');
        const title = h1 ? h1.textContent.trim() : '';
        const article = document.querySelector('article') || document.querySelector('.article-content') || document.querySelector('.content') || document.querySelector('main');
        const body = article ? article.innerText.slice(0, 5000) : document.body.innerText.slice(0, 5000);
        return JSON.stringify({date: dt, title, body: body.slice(0,500), bodyLen: body.length});
    }"""
    resp = req("POST", f"/tabs/{tid}/evaluate", {"expression": js_data})
    data = json.loads(resp.get("result","{}"))
    
    dt = data.get('date','')
    print(f"\n[{i+1}] {a['title'][:65]}")
    print(f"    Date: '{dt}'")
    
    if dt:
        try:
            pub = datetime.fromisoformat(dt.replace('Z','+00:00'))
            within = pub >= CUTOFF
            print(f"    Parsed: {pub.isoformat()} \u2192 within_36h={within}")
        except Exception as e:
            print(f"    Failed to parse: {e}")
    
    # Look for album/artist in body
    body = data.get('body','')
    print(f"    Body preview: {body[:200].strip()}")
    
    req("DELETE", f"/tabs/{tid}")
    time.sleep(1)
