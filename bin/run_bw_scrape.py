#!/usr/bin/env python3
"""
scrape_bandwagon_asia.py — Modified for this run.
Uses --http1.1 style (urllib default is HTTP/1.1) and longer timeouts.
"""
import argparse, json, re, sys, urllib.error, urllib.request
from datetime import datetime, timezone, timedelta

LISTING_URLS = [
    "https://www.bandwagon.asia/articles",
    "https://www.bandwagon.asia/categories/music-reviews",
]
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
SITE_ID = "bandwagon_asia"
SOURCE = "Bandwagon Asia"
TAGS = "asia,music,news"
REQUEST_TIMEOUT = 120  # Increased from 15s to 120s — site is very slow

NON_MUSIC_TOKENS = ("(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)")
DATA_ARTICLES_RE = re.compile(r'data-articles="([^"]+)"')

def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        sys.stderr.write(f"  [WARN] GET {url} failed: {e}\n")
        return ""

def parse_listing(html: str) -> list:
    m = DATA_ARTICLES_RE.search(html)
    if not m:
        return []
    raw_json = m.group(1)
    unescaped = raw_json.replace("&quot;", '"').replace("&amp;", "&").replace("&#x2F;", "/").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    try:
        data = json.loads(unescaped)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"  [WARN] JSON parse error: {e}\n")
        return []
    edges = data.get("edges", [])
    items = []
    for edge in edges:
        node = edge.get("node", {})
        slug = node.get("slug", "")
        url = node.get("url", "") or ("https://www.bandwagon.asia/articles/" + slug if slug else "")
        items.append({
            "slug": slug,
            "title": node.get("title", ""),
            "url": url,
            "author": node.get("author", ""),
            "categories": [c.get("name", "") for c in node.get("categories", [])],
            "spins": node.get("spins", ""),
        })
    return items

PUBDATE_RE = re.compile(r'<time\s+class="article--publish-date"\s+datetime="([^"]+)"')
UPDATED_RE = re.compile(r'<time\s+class="article--updated-date"\s+datetime="([^"]+)"')
ARTICLE_CONTENT_RE = re.compile(r'<section\s+class="article__content"[^>]*>(.*?)</section>\s*<div\s+class="like-container"', re.DOTALL)
ARTICLE_CONTENT_ALT_RE = re.compile(r'<section\s+class="article__content"[^>]*>(.*?)</section>', re.DOTALL)
ARTICLE_CATS_RE = re.compile(r'class="article__category-link"[^>]*>([^<]+)</a>')
ARTICLE_AUTHOR_RE = re.compile(r'<a\s+href="/users/[^"]+"\s+rel="author"\s+class="article__author">([^<]+)</a>')

def html_to_text(html: str) -> str:
    html = re.sub(r'<img[^>]+/?>', '', html)
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<p[^>]*>', '\n', html)
    html = re.sub(r'</p>', '\n', html)
    html = re.sub(r'<br\s*/?>', '\n', html)
    html = re.sub(r'</?(strong|em|b|i|u|span|a)[^>]*>', '', html)
    html = re.sub(r'<[^>]+>', '', html)
    html = html.replace("&quot;", '"').replace("&amp;", "&").replace("&#x27;", "'").replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    html = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), html)
    html = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), html)
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in html.split('\n')]
    lines = [ln for ln in lines if ln]
    return '\n\n'.join(lines)

def parse_article(html: str) -> dict:
    out = {"pub_date": "", "updated": "", "body": "", "categories": [], "author": ""}
    m = PUBDATE_RE.search(html)
    if m:
        out["pub_date"] = m.group(1)
    m = UPDATED_RE.search(html)
    if m:
        out["updated"] = m.group(1)
    out["categories"] = ARTICLE_CATS_RE.findall(html)
    m = ARTICLE_AUTHOR_RE.search(html)
    if m:
        out["author"] = m.group(1).strip()
    m = ARTICLE_CONTENT_RE.search(html)
    if not m:
        m = ARTICLE_CONTENT_ALT_RE.search(html)
    if m:
        out["body"] = html_to_text(m.group(1))
    return out

def iso_to_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        if "+" in iso or iso.endswith("Z"):
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).date().isoformat()
        return datetime.fromisoformat(iso).date().isoformat()
    except ValueError:
        try:
            return datetime.strptime(iso[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return ""

def classify_type(categories: list) -> str:
    cats_lower = {c.lower() for c in categories}
    if "review" in cats_lower:
        return "review"
    return "feature"

def main():
    parser = argparse.ArgumentParser(description="Scrape Bandwagon Asia")
    parser.add_argument("--days", type=float, default=1.5)
    parser.add_argument("--date", type=str, default=None)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    if args.date:
        cutoff_dt = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        cutoff_dt = now - timedelta(days=args.days)
    cutoff_date = cutoff_dt.date()

    sys.stderr.write(f"Bandwagon Asia scraper — Now (UTC): {now.isoformat()}, Cutoff (UTC): {cutoff_dt.isoformat()}\n")

    listing = []
    for url in LISTING_URLS:
        sys.stderr.write(f"Phase 1: Fetching {url}...\n")
        html = http_get(url)
        if not html:
            sys.stderr.write(f"  Empty response, skip\n")
            continue
        items_here = parse_listing(html)
        sys.stderr.write(f"  Found {len(items_here)} articles\n")
        existing = {x["url"] for x in listing}
        for it in items_here:
            if it["url"] not in existing:
                listing.append(it)
                existing.add(it["url"])
    sys.stderr.write(f"  Total unique candidates: {len(listing)}\n")
    
    if not listing:
        result = {"meta": {"total": 0, "scraped_at": now.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    items = []
    for idx, art in enumerate(listing):
        url = art["url"]
        title = art["title"]
        if not url or not title:
            continue
        if any(tok in title for tok in NON_MUSIC_TOKENS):
            sys.stderr.write(f"  Skipping non-music: {title[:80]}\n")
            continue

        sys.stderr.write(f"  [{idx+1}/{len(listing)}] {title[:80]}\n")
        article_html = http_get(url)
        if not article_html:
            continue

        parsed = parse_article(article_html)
        pub_date_iso = parsed["pub_date"]
        pub_date = iso_to_date(pub_date_iso)

        if pub_date_iso:
            try:
                item_dt = datetime.fromisoformat(pub_date_iso)
                if item_dt < cutoff_dt:
                    sys.stderr.write(f"    → {pub_date} {pub_date_iso} (older than cutoff, skip)\n")
                    continue
            except ValueError:
                try:
                    item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                    if item_date < cutoff_date:
                        sys.stderr.write(f"    → {pub_date} (older than cutoff, skip)\n")
                        continue
                except ValueError:
                    sys.stderr.write(f"    → bad pub_date, skip\n")
                    continue
        else:
            sys.stderr.write(f"    → no pub_date, skip\n")
            continue

        item_type = classify_type(parsed["categories"] or art["categories"])
        body = parsed["body"] or ""
        items.append({
            "album": title.strip(),
            "artist": "",
            "score": None,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": TAGS,
            "excerpt": body[:500] if body else "",
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": item_type,
        })
        sys.stderr.write(f"    → {pub_date} type={item_type} body={len(body)} chars\n")

    items.sort(key=lambda x: x.get("pub_date", "0000-00-00"), reverse=True)
    result = {"meta": {"total": len(items), "scraped_at": now.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": items}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"\nDone. {len(items)} items in 36h window.\n")

if __name__ == "__main__":
    main()
