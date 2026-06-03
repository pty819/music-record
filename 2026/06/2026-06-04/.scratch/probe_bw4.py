#!/usr/bin/env python3
"""Extract full page content from Bandwagon articles."""
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

# Extract articles from reviews category page
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
        const imgLink = b.querySelector('.article-block__image a, .article-block__image img');
        const imgUrl = imgLink ? (imgLink.href || imgLink.src) : '';
        // Try to find date
        const timeEl = b.querySelector('time, [datetime]');
        let dateText = '';
        if (timeEl) dateText = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
        // Category
        const catEl = b.querySelector('[class*=category], [class*=tag], .meta, .info');
        const category = catEl ? catEl.textContent.trim() : '';
        const excerptEl = b.querySelector('.article-block__body, p, .excerpt');
        const excerpt = excerptEl ? excerptEl.textContent.trim().slice(0,300) : '';
        items.push({title, url, excerpt, dateText, category, imgUrl});
    });
    return JSON.stringify(items);
}"""
resp = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js})
raw = resp.get("result","[]")
articles = json.loads(raw) if isinstance(raw, str) else raw

print(f"=== Reviews category: {len(articles)} articles ===")
for a in articles:
    print(f"  date={a.get('dateText','?')[:20]} | {a['title'][:60]}")
    print(f"     -> {a['url']}")

# Check if there are dates in the page at all
js2 = """() => {
    const dates = [];
    document.querySelectorAll('time, [datetime], .date, .published, .meta span, .info span').forEach(el => {
        const t = el.textContent.trim();
        if (t.match(/\\d{4}/)) dates.push({tag: el.tagName, text: t, datetime: el.getAttribute('datetime') || ''});
    });
    return JSON.stringify(dates);
}"""
resp2 = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js2})
dates = json.loads(resp2.get("result","[]"))
print(f"\n=== Date elements on page ===")
for d in dates:
    print(f"  <{d['tag']}> datetime={d['datetime']} | text={d['text'][:60]}")

# Check if there's pagination
js3 = """() => {
    const pagers = [];
    document.querySelectorAll('.pagination, .pager, .next, .prev, a[rel=next], a[rel=prev], [class*=page], [class*=pagin]').forEach(el => {
        const txt = el.textContent.trim().slice(0,40);
        const href = el.href || '';
        pagers.push({tag: el.tagName, class: el.className.slice(0,40), text: txt, href});
    });
    return JSON.stringify(pagers);
}"""
resp3 = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js3})
pagers = json.loads(resp3.get("result","[]"))
print(f"\n=== Pagination ===")
for p in pagers:
    print(f"  <{p['tag']}>.{p['class']} '{p['text']}' -> {p['href'][:80]}")

req("DELETE", f"/tabs/{tab_id}")

# Now fetch the actual article page to see its structure
print("\n\n=== Fetching first article for structure ===")
url = articles[0]['url'] if articles else 'https://www.bandwagon.asia/articles/lola-amour-mark-10-years-with-emotional-sold-out-anniversary-shows-at-123-block-gig-report'
tab2 = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":url})
tab_id2 = tab2.get("tabId","")
time.sleep(2)

# Get article body
js_body = """() => {
    // Try article, main content, or body
    const article = document.querySelector('article') || document.querySelector('.article-content') || document.querySelector('.content') || document.querySelector('main');
    const body = article ? article.innerText.slice(0, 8000) : document.body.innerText.slice(0, 8000);
    
    // Get metadata
    const meta = {};
    const titleEl = document.querySelector('h1');
    meta.title = titleEl ? titleEl.textContent.trim() : '';
    
    const timeEl = document.querySelector('time, [datetime], .published, .date');
    if (timeEl) {
        meta.date = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
        meta.dateTag = timeEl.tagName;
    }
    
    const authorEl = document.querySelector('[rel=author], .author, .byline, [class*=author]');
    meta.author = authorEl ? authorEl.textContent.trim() : '';
    
    return JSON.stringify({body: body.slice(0,4000), meta});
}"""
resp_body = req("POST", f"/tabs/{tab_id2}/evaluate", {"expression": js_body})
article_data = json.loads(resp_body.get("result","{}"))
print(f"\n=== Article: {article_data.get('meta',{}).get('title','')} ===")
print(f"Meta: {article_data.get('meta',{})}")
print(f"Body (first 1500):\n{article_data.get('body','')[:1500]}")

req("DELETE", f"/tabs/{tab_id2}")
