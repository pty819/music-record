#!/usr/bin/env python3
"""Probe Bandwagon Asia reviews page HTML structure."""
import json, urllib.request, sys, time

CAMOFOX = "http://127.0.0.1:9377"

def req(method, path, body=None):
    url = f"{CAMOFOX}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())

tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":"https://www.bandwagon.asia/categories/review"})
tab_id = tab.get("tabId","")
time.sleep(3)

# Get full page HTML inner structure via innerHTML of main sections
js = """() => {
    // Get all headings and their parent containers
    const items = [];
    const headings = document.querySelectorAll('h1, h2, h3, h4');
    headings.forEach(h => {
        const title = h.textContent.trim();
        if (!title || title.length < 3) return;
        const parent = h.closest('a') || h.closest('article') || h.parentElement;
        const link = h.closest('a') || h.querySelector('a');
        const href = link ? link.href : '';
        items.push({
            tag: h.tagName,
            title: title.slice(0,100),
            href: href,
            parentTag: parent ? parent.tagName : '',
            parentClass: parent ? parent.className.slice(0,100) : ''
        });
    });
    return JSON.stringify(items);
}"""
resp = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js})
items = json.loads(resp.get("result","[]"))
print(f"=== Headings ({len(items)}) ===")
for it in items:
    print(f"  <{it['tag']}> {it['title'][:70]} href={it['href'][:80]} parent={it['parentTag']}.{it['parentClass']}")

# Get all links with full context
js2 = """() => {
    return JSON.stringify(
        Array.from(document.querySelectorAll('a')).map(a => ({
            text: a.textContent.trim().slice(0,80),
            href: a.href,
            parentTag: a.parentElement ? a.parentElement.tagName : '',
            parentClass: a.parentElement ? a.parentElement.className.slice(0,80) : '',
        }))
    );
}"""
resp2 = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js2})
links = json.loads(resp2.get("result","[]"))
print(f"\n=== ALL links ({len(links)}) ===")
for l in links[:50]:
    if '/articles/' in l['href']:
        print(f"  [{l['parentTag']}.{l['parentClass']}] '{l['text'][:60]}' -> {l['href']}")

# Get main content area HTML structure
js3 = """() => {
    return JSON.stringify({
        mainHTML: document.querySelector('main') ? document.querySelector('main').innerHTML.slice(0,3000) : 'no main',
        bodyClasses: document.body.className,
        articleCount: document.querySelectorAll('article').length,
        sectionCount: document.querySelectorAll('section').length,
    });
}"""
resp3 = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js3})
struct = json.loads(resp3.get("result","{}"))
print(f"\n=== Page structure ===")
print(f"body classes: {struct.get('bodyClasses','')}")
print(f"articles: {struct.get('articleCount',0)}, sections: {struct.get('sectionCount',0)}")
print(f"\nMain HTML (first 2000 chars):\n{struct.get('mainHTML','')[:2000]}")

req("DELETE", f"/tabs/{tab_id}")
