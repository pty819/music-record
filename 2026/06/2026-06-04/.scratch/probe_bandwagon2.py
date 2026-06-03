#!/usr/bin/env python3
"""Probe Bandwagon Asia Reviews and Listen categories."""
import json, urllib.request, sys, time

CAMOFOX = "http://127.0.0.1:9377"

def req(method, path, body=None):
    url = f"{CAMOFOX}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())

def snap(tab_id):
    js = """() => {
        const articles = [];
        const sel = document.querySelectorAll('article, [class*=post], [class*=card], [class*=item], li[class*=post], div[class*=entry]');
        sel.forEach(s => {
            const h = s.querySelector('h1, h2, h3, h4');
            if (!h) return;
            const title = h.textContent.trim();
            if (!title || title.length < 5) return;
            const link = h.querySelector('a');
            const url = link ? link.href : '';
            const img = s.querySelector('img');
            const imgSrc = img ? img.src : '';
            const p = s.querySelector('p, .excerpt, .summary, .description');
            const excerpt = p ? p.textContent.trim().slice(0,200) : '';
            const timeEl = s.querySelector('time, [datetime], .date, .pub-date');
            let dateText = '';
            if (timeEl) dateText = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
            const cat = s.querySelector('[class*=category], [class*=tag], [class*=section]');
            const category = cat ? cat.textContent.trim() : '';
            articles.push({title, url, excerpt, dateText, category, imgSrc});
        });
        return JSON.stringify(articles.slice(0,40));
    }"""
    resp = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js})
    raw = resp.get("result","[]")
    return json.loads(raw) if isinstance(raw, str) else raw

for path, label in [("/categories/review", "Reviews"), ("/categories/listen", "Listen"), ("/categories/feature", "Features")]:
    try:
        tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":f"https://www.bandwagon.asia{path}"})
        tab_id = tab.get("tabId","")
        time.sleep(2)
        title = req("POST", f"/tabs/{tab_id}/evaluate", {"expression":"() => document.title"})
        print(f"\n=== {label} ({path}) ===")
        print(f"Title: {title.get('result','')}")
        articles = snap(tab_id)
        print(f"Found {len(articles)} articles/items")
        for a in articles[:20]:
            print(f"  [{a.get('dateText','?')}] {a.get('title','')[:70]}")
            print(f"     -> {a.get('url','')}")
            if a.get('excerpt'):
                print(f"     -> {a.get('excerpt','')[:80]}")
        req("DELETE", f"/tabs/{tab_id}")
    except Exception as e:
        print(f"Error on {path}: {e}")
