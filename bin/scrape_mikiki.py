#!/usr/bin/env python3
"""
scrape_mikiki.py — Scrape Mikiki (mikiki.tokyo.jp) for music reviews.

Strategy:
- Review listing: https://mikiki.tokyo.jp/list/review
- Article links: /articles/-/NNNNN
- Each article page has: h1 title, date, body content
- Uses concurrent fetching for speed.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

SITE_ID = "mikiki"
SOURCE = "Mikiki"
BASE = "https://mikiki.tokyo.jp"
LIST_URL = f"{BASE}/list/review"


def fetch(url, timeout=20):
    try:
        result = subprocess.run(
            ["curl", "-sL", "-A", "Mozilla/5.0", "-m", str(timeout), url],
            capture_output=True, timeout=timeout + 5,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""


def parse_date_jp(date_str):
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except ValueError:
            pass
    return None


def parse_listing(html):
    articles = []
    cards = re.findall(r'<article[^>]*>(.*?)</article>', html, re.S)
    for card in cards:
        link_m = re.search(r'href="(/articles/-/\d+)"', card)
        if not link_m:
            continue
        url = BASE + link_m.group(1)

        date_m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', card)
        pub_date = parse_date_jp(date_m.group(1)) if date_m else None

        # genre
        genre_m = re.search(r'c-genre[^>]*>([^<]+)', card)
        genre = genre_m.group(1).strip() if genre_m else ""

        # title from h2
        title_m = re.search(r'm-article__ttl[^>]*>([^<]+)', card)
        title = title_m.group(1).strip() if title_m else ""

        articles.append({"url": url, "pub_date": pub_date, "title": title, "genre": genre})
    return articles


def parse_article(url):
    html = fetch(url)
    if not html:
        return None

    # Title from h1
    title_m = re.search(r'<h1[^>]*>([^<]+)', html)
    title = title_m.group(1).strip() if title_m else ""

    # Date
    date_m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', html)
    pub_date = parse_date_jp(date_m.group(1)) if date_m else None

    # Body: try multiple selectors
    body = ""
    for pattern in [
        r'class="[^"]*article[_-]?body[^"]*"[^>]*>(.*?)</div>',
        r'class="[^"]*entry[_-]?content[^"]*"[^>]*>(.*?)</div>',
        r'class="[^"]*post[_-]?content[^"]*"[^>]*>(.*?)</div>',
    ]:
        body_m = re.search(pattern, html, re.S)
        if body_m:
            body = re.sub(r'<[^>]+>', ' ', body_m.group(1))
            body = re.sub(r'\s+', ' ', body).strip()
            body = body.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            body = body.replace('&quot;', '"').replace('&#39;', "'")
            if len(body) > 50:
                break

    # If no body found, try to get text from the main content area
    if not body or len(body) < 50:
        main_m = re.search(r'<main[^>]*>(.*?)</main>', html, re.S)
        if main_m:
            text = re.sub(r'<[^>]+>', ' ', main_m.group(1))
            text = re.sub(r'\s+', ' ', text).strip()
            # Skip the first part (navigation etc), take middle content
            if len(text) > 200:
                body = text[200:2200]

    # Tags
    tags = re.findall(r'class="[^"]*tag[^"]*"[^>]*>([^<]+)', html)
    tags = [t.strip() for t in tags if t.strip()]

    return {"title": title, "pub_date": pub_date, "body": body, "tags": tags}


def scrape(ref_date, days=1.5, max_workers=8):
    cutoff = ref_date - timedelta(days=days)

    html = fetch(LIST_URL)
    if not html:
        return {"meta": {"total": 0, "error": "listing page fetch failed"}, "items": []}

    articles = parse_listing(html)

    # Filter by date first
    filtered = []
    for art in articles:
        if art["pub_date"] and art["pub_date"] < cutoff:
            continue
        filtered.append(art)

    # Fetch article pages concurrently
    def fetch_one(art):
        parsed = parse_article(art["url"])
        if not parsed:
            return None
        pub_date = parsed["pub_date"] or art["pub_date"]
        if pub_date and pub_date < cutoff:
            return None
        title = parsed["title"] or art["title"]
        artist, album = "", title
        for sep in [" — ", " – ", " / ", "｜"]:
            parts = title.split(sep, 1)
            if len(parts) == 2:
                artist, album = parts[0].strip(), parts[1].strip()
                break
        tags_str = " ".join(parsed["tags"])
        if art.get("genre") and art["genre"] not in tags_str:
            tags_str = art["genre"] + " " + tags_str
        return {
            "album": album,
            "artist": artist,
            "score": None,
            "url": art["url"],
            "source": SOURCE,
            "pub_date": pub_date.isoformat() if pub_date else "",
            "tags": tags_str.strip(),
            "excerpt": parsed["body"][:500] if parsed["body"] else "",
            "body": parsed["body"],
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        }

    items = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, art): art for art in filtered}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    items.append(result)
            except Exception as e:
                sys.stderr.write(f"  error: {e}\n")

    items.sort(key=lambda x: x.get("pub_date", ""), reverse=True)
    return {
        "meta": {
            "total": len(items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff.isoformat(),
        },
        "items": items,
    }


def main():
    parser = argparse.ArgumentParser(description="Mikiki review scraper")
    parser.add_argument("--days", type=float, default=1.5)
    parser.add_argument("--date", help="reference date YYYY-MM-DD")
    args = parser.parse_args()

    ref_date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                if args.date else datetime.now(timezone.utc).date())

    result = scrape(ref_date, args.days)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stderr.write(f"Done: {result['meta']['total']} items\n")


if __name__ == "__main__":
    main()
