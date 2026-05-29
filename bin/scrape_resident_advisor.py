#!/usr/bin/env python3
"""
scrape_resident_advisor.py — Scrape Resident Advisor reviews (ra.co/reviews)
Fetches list page, then visits each article for full body text.
Outputs standardized JSON with excerpt + body fields.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

BASE = "https://ra.co"


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scrape Resident Advisor reviews")
    p.add_argument("--days", type=float, default=1.5, help="Days back from reference date")
    p.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    return p.parse_args()


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_date(text):
    text = text.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def fetch_article_body(article_url):
    """Fetch full article page and extract body text, return (body, excerpt)."""
    try:
        html = fetch(article_url)
        soup = BeautifulSoup(html, "lxml")
        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()

        # Try to find the main article content area
        body_el = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|body|post|entry|review", re.I))
            or soup.find("section", class_=re.compile(r"content|body|post|entry|review", re.I))
        )
        if not body_el:
            body_el = soup

        body = body_el.get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body).strip()
        excerpt = body[:500]
        return body, excerpt
    except Exception:
        return "", ""


def main():
    args = parse_args()
    ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(timezone.utc).date()
    cutoff = ref_date - timedelta(days=args.days)

    list_url = f"{BASE}/reviews"
    html = fetch(list_url)
    soup = BeautifulSoup(html, "lxml")

    items = []
    seen = set()
    for card in soup.find_all("div", class_=re.compile(r"review|article-card|card", re.I)):
        link = card.find("a", href=True)
        if not link:
            continue
        href = link.get("href", "")
        full_url = f"{BASE}{href}" if href.startswith("/") else href
        if not full_url.startswith("http") or full_url in seen:
            continue
        seen.add(full_url)

        title = (link.get_text(strip=True) or "").strip()
        if not title or len(title) < 3:
            continue

        # Date
        date_text = ""
        date_el = card.find("time") or card.find(class_=re.compile(r"date|time", re.I))
        if date_el:
            date_text = date_el.get_text(strip=True)
        else:
            m = re.search(
                r"(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+\d+,\s+\d{4}",
                card.get_text(),
            )
            if m:
                date_text = m.group(0)
        pub_date = parse_date(date_text) if date_text else None
        if pub_date and pub_date < cutoff:
            continue

        # Fetch full article body
        body, excerpt = fetch_article_body(full_url)

        # If body fetch failed, fallback to list-page excerpt
        if not body:
            text = card.get_text(" ", strip=True)
            excerpt = text.replace(title, "", 1).strip()[:500].replace("\n", " ")
            body = ""

        # Artist from title (RA format: "Artist - Title")
        artist = ""
        if " - " in title:
            parts = title.split(" - ", 1)
            artist = parts[0].strip()
            album = parts[1].strip()
        else:
            album = title

        items.append({
            "album": album,
            "artist": artist,
            "score": None,
            "url": full_url,
            "source": "Resident Advisor",
            "pub_date": pub_date.isoformat() if pub_date else "",
            "tags": "electronic",
            "excerpt": excerpt,
            "body": body,
            "site_id": "resident_advisor",
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
    sys.stderr.write(f"RA: {len(items)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
