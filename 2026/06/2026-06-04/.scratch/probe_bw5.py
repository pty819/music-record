#!/usr/bin/env python3
"""Check Bandwagon Asia full article dates and Listen category."""
import json, urllib.request, sys, time, re
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

# Check the reviews articles dates by visiting each one
tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":"https://www.bandwagon.asia/categories/review"})
tab_id = tab.get("tabId","")
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
resp = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js})
articles = json.loads(resp.get("result","[]"))
req("DELETE", f"/tabs/{tab_id}")

print(f"Found {len(articles)} articles in reviews")
for a in articles:
    print(f"  {a['title'][:65]}")

# Check dates on each article
print(f"\nChecking article dates (cutoff = {CUTOFF.isoformat()})...")
for i, a in enumerate(articles):
    print(f"\n--- [{i+1}/{len(articles)}] {a['title'][:50]} ---")
    tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":a['url']})
    tid = tab.get("tabId","")
    time.sleep(2)
    
    js_date = """() => {
        const timeEl = document.querySelector('time');
        let dt = '';
        if (timeEl) dt = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
        const h1 = document.querySelector('h1');
        const title = h1 ? h1.textContent.trim() : '';
        
        // Get body
        const article = document.querySelector('article') || document.querySelector('.article-content') || document.querySelector('.content') || document.querySelector('main');
        const body = article ? article.innerText.slice(0, 5000) : document.body.innerText.slice(0, 5000);
        
        // Check for album/artist mentions
        return JSON.stringify({date: dt, title, body: body.slice(0,1000), bodyLen: body.length});
    }"""
    resp = req("POST", f"/tabs/{tid}/evaluate", {"expression": js_date})
    data = json.loads(resp.get("result","{}"))
    
    dt = data.get('date','')
    print(f"  Date: '{dt}'")
    
    if dt:
        try:
            pub = datetime.fromisoformat(dt.replace('Z','+00:00'))
            within = pub >= CUTOFF
            print(f"  Parsed: {pub.isoformat()} within_36h={within}")
        except:
            print(f"  Could not parse date")
    else:
        print(f"  No date found")
    
    req("DELETE", f"/tabs/{tid}")
    time.sleep(1)

# Also check Listen category
print("\n\n=== Listen category ===")
try:
    tab3 = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":"https://www.bandwagon.asia/categories/listen"})
    tid3 = tab3.get("tabId","")
    time.sleep(2)
    resp3 = req("POST", f"/tabs/{tid3}/evaluate", {"expression":"() => document.title"})
    print(f"Title: {resp3.get('result','')}")
    
    js_arts = """() => {
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
    resp3b = req("POST", f"/tabs/{tid3}/evaluate", {"expression": js_arts})
    arts3 = json.loads(resp3b.get("result","[]"))
    print(f"Found {len(arts3)} articles")
    for a3 in arts3[:10]:
        print(f"  {a3['title'][:60]}")
    
    req("DELETE", f"/tabs/{tid3}")
except Exception as e:
    print(f"Error: {e}")
