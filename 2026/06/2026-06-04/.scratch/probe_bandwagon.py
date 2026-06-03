#!/usr/bin/env python3
"""Probe Bandwagon Asia site structure."""
import json, urllib.request, sys, time

CAMOFOX = "http://127.0.0.1:9377"

def req(method, path, body=None):
    url = f"{CAMOFOX}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())

# Create tab on homepage
tab = req("POST", "/tabs", {"userId":"bw", "sessionKey":"bw", "url":"https://www.bandwagon.asia/"})
tab_id = tab.get("tabId","")
print(f"tabId: {tab_id}")
print(f"title: {tab.get('title','')}")
time.sleep(3)

# Get all links
js_links = """() => {
    const items = [];
    const links = document.querySelectorAll('a[href]');
    const seen = new Set();
    links.forEach(a => {
        const t = a.textContent.trim().slice(0,120);
        const h = a.href;
        if (t.length > 3 && h && !seen.has(h)) {
            seen.add(h);
            items.push({text: t, href: h});
        }
    });
    return JSON.stringify(items);
}"""
resp = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js_links})
links = json.loads(resp.get("result","[]"))
print(f"\n=== All links ({len(links)}) ===")
for l in links[:60]:
    print(f"  {l['text'][:80]} -> {l['href']}")

# Look for article/review links
print(f"\n=== Music/review links ===")
music_links = [l for l in links if any(k in l['href'].lower() for k in ['/music/', '/review/', '/album/', '/feature/', '/news/'])]
print(f"Found {len(music_links)} music/review links:")
for l in music_links[:30]:
    print(f"  {l['text'][:80]} -> {l['href']}")

# Also check navigation / menu
js_nav = """() => {
    return JSON.stringify({
        nav: Array.from(document.querySelectorAll('nav a, header a, .menu a, [class*=nav] a, [class*=menu] a')).map(a => ({text: a.textContent.trim().slice(0,80), href: a.href})),
        sections: Array.from(document.querySelectorAll('main section, #content section, .content section')).slice(0,10).map(s => s.id || s.className || 'no-id').join(', '),
    });
}"""
resp2 = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js_nav})
nav = json.loads(resp2.get("result","{}"))
print(f"\n=== Navigation ===")
for n in nav.get('nav', []):
    if n['text']:
        print(f"  {n['text'][:60]} -> {n['href']}")
print(f"\nSections: {nav.get('sections','')}")

# Close tab
req("DELETE", f"/tabs/{tab_id}")
