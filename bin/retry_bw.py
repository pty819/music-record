#!/usr/bin/env python3
"""Retry failed article fetches and music-reviews listing."""
import json, re, sys, urllib.error, urllib.request
from datetime import datetime, timezone, timedelta

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
SITE_ID = "bandwagon_asia"
SOURCE = "Bandwagon Asia"
TAGS = "asia,music,news"
TIMEOUT = 120

# Failed URLs from first run
FAILED_URLS = [
    "https://www.bandwagon.asia/articles/over-34-000-fans-gather-to-see-enhypen-rain-lesserafim-more-at-2026-weverse-con-festival",
    "https://www.bandwagon.asia/articles/p-pop-group-ygig-dive-into-summer-nostalgia-on-vibrant-single-perfect-blue-listen",
    "https://www.bandwagon.asia/articles/iiso-unpacks-the-complications-of-love-in-best-friend-along-with-nostalgic-y2k-inspired-mv-watch",
    "https://www.bandwagon.asia/articles/tensions-soar-among-bts-army-in-singapore-as-scalpers-resellers-emerge-during-arirang-tour-ticket-sales",
]

DATA_ARTICLES_RE = re.compile(r'data-articles="([^"]+)"')
PUBDATE_RE = re.compile(r'<time\s+class="article--publish-date"\s+datetime="([^"]+)"')
ARTICLE_CONTENT_ALT_RE = re.compile(r'<section\s+class="article__content"[^>]*>(.*?)</section>', re.DOTALL)
ARTICLE_CATS_RE = re.compile(r'class="article__category-link"[^>]*>([^<]+)</a>')

def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        sys.stderr.write(f"  FAIL: {e}\n")
        return ""

def html_to_text(html):
    html = re.sub(r'<img[^>]+/?>', '', html)
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<p[^>]*>', '\n', html)
    html = re.sub(r'</p>', '\n', html)
    html = re.sub(r'<br\s*/?>', '\n', html)
    html = re.sub(r'</?(strong|em|b|i|u|span|a)[^>]*>', '', html)
    html = re.sub(r'<[^>]+>', '', html)
    html = html.replace("&quot;", '"').replace("&amp;", "&").replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    html = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), html)
    html = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), html)
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in html.split('\n')]
    lines = [ln for ln in lines if ln]
    return '\n\n'.join(lines)

now = datetime.now(timezone.utc)
cutoff_dt = now - timedelta(days=1.5)

items = []

# 1. Try music-reviews listing
sys.stderr.write("=== Retry /categories/music-reviews ===\n")
html = http_get("https://www.bandwagon.asia/categories/music-reviews")
if html:
    m = DATA_ARTICLES_RE.search(html)
    if m:
        raw = m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&#x2F;", "/").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
        data = json.loads(raw)
        for edge in data.get("edges", []):
            n = edge.get("node", {})
            url = n.get("url", "")
            title = n.get("title", "")
            sys.stderr.write(f"  Review: {title[:70]}\n  URL: {url}\n")
            art_html = http_get(url)
            if art_html:
                pm = PUBDATE_RE.search(art_html)
                if pm:
                    pub_iso = pm.group(1)
                    try:
                        item_dt = datetime.fromisoformat(pub_iso)
                        sys.stderr.write(f"  Date: {pub_iso}\n")
                        if item_dt >= cutoff_dt:
                            cats = ARTICLE_CATS_RE.findall(art_html)
                            cm = ARTICLE_CONTENT_ALT_RE.search(art_html)
                            body = html_to_text(cm.group(1)) if cm else ""
                            item_type = "review" if "review" in {c.lower() for c in cats} else "feature"
                            date_str = item_dt.date().isoformat()
                            items.append({
                                "album": title.strip(),
                                "artist": "",
                                "score": None,
                                "url": url,
                                "source": SOURCE,
                                "pub_date": date_str,
                                "tags": TAGS,
                                "excerpt": body[:500] if body else "",
                                "body": body,
                                "site_id": SITE_ID,
                                "crawl_status": "success",
                                "type": item_type,
                            })
                            sys.stderr.write(f"  → INCLUDED ({date_str})\n")
                        else:
                            sys.stderr.write(f"  → OLDER than cutoff\n")
                    except:
                        sys.stderr.write(f"  → bad date\n")
                else:
                    sys.stderr.write(f"  → no pub_date\n")

# 2. Retry failed URLs
sys.stderr.write("\n=== Retry failed article URLs ===\n")
for url in FAILED_URLS:
    sys.stderr.write(f"Retrying: {url[:70]}\n")
    art_html = http_get(url)
    if art_html:
        pm = PUBDATE_RE.search(art_html)
        if pm:
            pub_iso = pm.group(1)
            try:
                item_dt = datetime.fromisoformat(pub_iso)
                sys.stderr.write(f"  Date: {pub_iso}\n")
                if item_dt >= cutoff_dt:
                    cats = ARTICLE_CATS_RE.findall(art_html)
                    cm = ARTICLE_CONTENT_ALT_RE.search(art_html)
                    body = html_to_text(cm.group(1)) if cm else ""
                    # Get title
                    tm = re.search(r'<title>([^<]+)</title>', art_html)
                    title = tm.group(1) if tm else url.split("/")[-1]
                    date_str = item_dt.date().isoformat()
                    items.append({
                        "album": title.strip(),
                        "artist": "",
                        "score": None,
                        "url": url,
                        "source": SOURCE,
                        "pub_date": date_str,
                        "tags": TAGS,
                        "excerpt": body[:500] if body else "",
                        "body": body,
                        "site_id": SITE_ID,
                        "crawl_status": "success",
                        "type": "feature",
                    })
                    sys.stderr.write(f"  → INCLUDED ({date_str})\n")
                else:
                    sys.stderr.write(f"  → OLDER than cutoff\n")
            except:
                sys.stderr.write(f"  → bad date\n")
        else:
            sys.stderr.write(f"  → no pub_date\n")

# Output
if items:
    print(json.dumps({"meta": {"total": len(items), "scraped_at": now.isoformat(), "cutoff_date": cutoff_dt.date().isoformat()}, "items": items}, indent=2, ensure_ascii=False))
else:
    print(json.dumps({"meta": {"total": 0, "scraped_at": now.isoformat(), "cutoff_date": cutoff_dt.date().isoformat()}, "items": []}))
sys.stderr.write(f"\nRetry done. {len(items)} additional items.\n")
