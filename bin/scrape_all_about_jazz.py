#!/usr/bin/env python3
"""
scrape_all_about_jazz.py — Scrape All About Jazz reviews (allaboutjazz.com/reviews)
Fetches list page, then visits each article for full body text.
Outputs standardized JSON with excerpt + body fields.
"""
import json
import re
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

BASE_URL = "https://www.allaboutjazz.com"
LIST_URL = f"{BASE_URL}/reviews"


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scrape All About Jazz reviews")
    p.add_argument("--days", type=float, default=1.5, help="Days back from reference date")
    p.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    return p.parse_args()


def fetch(url):
    """Use curl to fetch a URL and return decoded HTML."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "30", url],
            capture_output=True, timeout=35
        )
        return result.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        sys.stderr.write(f"curl error fetching {url}: {e}\n")
        return ""


def parse_date(text):
    """Parse 'May 25, 2026' format."""
    text = text.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def fetch_article_body(article_url):
    """Fetch full article page and extract body text, return (body, excerpt)."""
    try:
        html = fetch(article_url)
        if not html:
            return "", ""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        # AAJ article content: try various selectors
        body_el = (
            soup.find("div", class_=re.compile(r"article-content|post-content|content-body|entry-content", re.I))
            or soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|body|post|entry|review", re.I))
        )
        if not body_el:
            body_el = soup
        text = body_el.get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", text).strip()
        excerpt = body[:500]
        return body, excerpt
    except Exception:
        return "", ""


def main():
    args = parse_args()
    ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(timezone.utc).date()
    cutoff = ref_date - timedelta(days=args.days)

    html = fetch(LIST_URL)
    if not html:
        sys.stderr.write("ERROR: Failed to fetch listing page\n")
        sys.exit(1)

    soup = BeautifulSoup(html, "lxml")
    items = []
    seen_urls = set()

    # AAJ review cards: div.card with h3 for album, p for meta
    cards = soup.find_all("div", class_=re.compile(r"card|review-card|review-item", re.I))
    if not cards:
        cards = soup.find_all("article")
    if not cards:
        cards = [soup]

    for card in (cards if len(cards) > 1 else [soup]):
        # Album title
        title_el = card.find(["h2", "h3", "h4"])
        if not title_el:
            continue
        album = title_el.get_text(strip=True)
        if not album or len(album) < 3:
            continue

        # Link
        link = title_el.find("a") or card.find("a", href=re.compile(r"/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+"))
        if not link:
            continue
        url = link.get("href", "")
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = BASE_URL + url
        if not url.startswith("http"):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Date
        date_text = ""
        date_el = card.find("time") or card.find(class_=re.compile(r"date|time|pub", re.I))
        if date_el:
            date_text = date_el.get_text(strip=True)
        else:
            text = card.get_text()
            m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,\s+\d{4}", text)
            if m:
                date_text = m.group(0)

        pub_date = parse_date(date_text) if date_text else None
        if pub_date is None or pub_date < cutoff:
            continue

        # Artist
        artist = ""
        artist_el = card.find(class_=re.compile(r"artist|author|reviewer", re.I))
        if artist_el:
            artist = artist_el.get_text(strip=True)

        # Fetch full article body
        body, excerpt = fetch_article_body(url)

        # Fallback excerpt from list page if body fetch failed
        if not body:
            excerpt_el = card.find(class_=re.compile(r"excerpt|summary|description|text", re.I)) or card.find("p")
            if excerpt_el:
                excerpt = excerpt_el.get_text(strip=True)[:500]
            body = ""

        items.append({
            "album": album,
            "artist": artist,
            "score": None,
            "url": url,
            "source": "All About Jazz",
            "pub_date": pub_date.isoformat() if pub_date else "",
            "tags": "jazz",
            "excerpt": excerpt,
            "body": body,
            "site_id": "all_about_jazz",
            "crawl_status": "success",
            "type": "review",
        })

    result = json.dumps({
        "meta": {
            "total": len(items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff.isoformat(),
        },
        "items": items,
    }, indent=2, ensure_ascii=False)

    print(result)
    sys.stderr.write(f"AAJ: {len(items)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
