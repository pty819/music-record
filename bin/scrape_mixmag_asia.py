#!/usr/bin/env python3
"""
scrape_mixmag_asia.py — Camoufox-based scraper for Mixmag Asia.

Mixmag Asia is primarily a music news/features site, not a review site.
Captures recent articles from the /music page.

Strategy:
  1. POST /tabs to create a tab and navigate to https://mixmag.asia/music
  2. Evaluate JS to extract articles (titles, URLs, dates, excerpts)
  3. For each article, navigate to its URL and fetch full body text
  4. Close tabs
  5. Output structured JSON to stdout

Output format:
  {"meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."}, "items": [
    {album, artist, score (None), url, source, pub_date (ISO or ''),
     tags='electronic,asia', excerpt (first 500 of body), body (full),
     site_id='mixmag_asia', crawl_status, type}
  ]}

Usage:
  python3 scrape_mixmag_asia.py [--days 2] [--date YYYY-MM-DD]
"""
import argparse
import json
import sys
import re
import urllib.request
import time
from datetime import datetime, timezone, timedelta

CAMOFOX = "http://127.0.0.1:9377"

# JS to get full body text from an article page
GET_BODY_JS = """
() => {
    const article = document.querySelector('article');
    if (article) return article.innerText.slice(0, 10000);
    return document.body.innerText.slice(0, 10000);
}
"""


def _req(method, path, body=None):
    import json as _json
    url = f"{CAMOFOX}{path}"
    data = _json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return _json.loads(r.read())


def extract_articles(tab_id):
    """Extract article data from the page DOM."""
    js = """(() => {
        const articles = [];
        const sections = document.querySelectorAll('section, div[class*="article"], div[class*="post"], div[class*="card"]');
        const seen = new Set();
        sections.forEach(s => {
            const h = s.querySelector('h2, h3, h4');
            if (!h) return;
            const title = h.textContent.trim();
            if (!title || title.length < 5) return;
            const link = h.querySelector('a');
            const url = link ? link.href : '';
            if (!url || seen.has(url)) return;
            seen.add(url);
            const p = s.querySelector('p');
            const excerpt = p ? p.textContent.trim().slice(0, 500) : '';
            // Try to find a date
            let dateText = '';
            const timeEl = s.querySelector('time');
            if (timeEl) dateText = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
            if (!dateText) {
                const cats = s.querySelectorAll('span, a');
                cats.forEach(c => {
                    const txt = c.textContent.trim();
                    const m = txt.match(/(January|February|March|April|May|June|July|August|September|October|November|December)\\\s+\\\d+,\\\s+\\\d{4}/);
                    if (m) dateText = m[0];
                });
            }
            const catEl = s.querySelector('[class*="category"], [class*="tag"], [class*="section"]');
            const category = catEl ? catEl.textContent.trim() : '';
            articles.push({title, url, excerpt, dateText, category});
        });
        // Also try to get articles from the grid/list layout
        const links = document.querySelectorAll('a[href*="/music/"], a[href*="/features/"]');
        links.forEach(a => {
            const title = a.textContent.trim();
            if (!title || title.length < 5) return;
            const url = a.href;
            if (seen.has(url)) return;
            seen.add(url);
            articles.push({title, url, excerpt: '', dateText: '', category: ''});
        });
        return JSON.stringify(articles);
    })()"""
    resp = _req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js})
    raw = resp.get("result", "[]")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def fetch_body(tab_id, url):
    """Navigate to a URL and fetch full body text."""
    try:
        _req("POST", f"/tabs/{tab_id}/navigate", {"url": url})
        time.sleep(2)
        resp = _req("POST", f"/tabs/{tab_id}/evaluate", {"expression": GET_BODY_JS})
        result = resp.get("result", "")
        if result is None:
            return ""
        return str(result).strip()[:10000]
    except Exception as e:
        sys.stderr.write(f"  ERROR fetching body for {url}: {e}\n")
        return ""


def parse_date(text):
    """Try to parse a date string into ISO date."""
    if not text:
        return None
    text = text.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Mixmag Asia articles"
    )
    parser.add_argument(
        "--days", type=float, default=1.5,
        help="Max age in days for articles (default: 2)"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Explicit cutoff date (YYYY-MM-DD). Overrides --days."
    )
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    if args.date:
        try:
            cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.stderr.write(f"ERROR: Invalid --date format '{args.date}'. Use YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        cutoff_date = today - timedelta(days=args.days)

    sys.stderr.write(
        f"Mixmag Asia scraper — Today: {today}, Cutoff: {cutoff_date}, "
        f"Days: {args.days}\n"
    )

    # Create tab and navigate to /music page
    tab = _req("POST", "/tabs", {
        "userId": "mixmag", "sessionKey": "mixmag",
        "url": "https://mixmag.asia/music"
    })
    tab_id = tab.get("tabId", "")
    if not tab_id:
        result = {
            "meta": {"total": 0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()},
            "items": []
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    try:
        time.sleep(3)  # Let page fully render
        articles = extract_articles(tab_id)

        items = []
        seen = set()
        total_articles = len(articles)
        for idx, a in enumerate(articles):
            title = a.get("title", "").strip()
            url = a.get("url", "")
            if not title or len(title) < 5 or url in seen:
                continue
            seen.add(url)

            excerpt = a.get("excerpt", "").strip()[:500]
            date_text = a.get("dateText", "")

            pub_date = parse_date(date_text)

            if pub_date and pub_date < cutoff_date:
                continue

            # Skip non-music articles
            cat = a.get("category", "").lower()
            if cat and cat not in ("music", "reviews", "features", "premiere", ""):
                continue

            # Fetch full body by navigating to the article page
            sys.stderr.write(f"  [{idx+1}/{total_articles}] Fetching body: {title[:60]}...\n")
            body = fetch_body(tab_id, url)

            # Determine type
            is_review = any(k in title.lower() for k in ["review:", "album review"])
            article_type = "review" if is_review else "feature"

            # Try to extract artist/album
            artist = ""
            album = title
            for sep in [" – ", " — ", " - "]:
                if sep in title:
                    parts = title.split(sep, 1)
                    artist = parts[0].strip()
                    album = parts[1].strip()
                    break

            items.append({
                "album": album,
                "artist": artist,
                "score": None,
                "url": url,
                "source": "Mixmag Asia",
                "pub_date": pub_date.isoformat() if pub_date else "",
                "tags": "electronic,asia",
                "excerpt": (excerpt or body)[:500],
                "body": body,
                "site_id": "mixmag_asia",
                "crawl_status": "success",
                "type": article_type,
            })

        result = json.dumps({
            "meta": {
                "total": len(items),
                "scraped_at": today.isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
            },
            "items": items
        }, indent=2, ensure_ascii=False)
        print(result)
        sys.stderr.write(f"Mixmag Asia: {len(items)} items\n")
    finally:
        try:
            _req("DELETE", f"/tabs/{tab_id}")
        except:
            pass


if __name__ == "__main__":
    main()
