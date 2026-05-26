#!/usr/bin/env python3
"""
scrape_dark_entries.py — Scraper for Dark Entries magazine (darkentries.be)
Fetches /recensies and homepage, then visits each article for full body text.
Outputs standardized JSON with excerpt + body fields.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

BASE = "https://darkentries.be"
RECENSIES_URL = f"{BASE}/recensies"
HOME_URL = BASE

# Dutch month name -> number mapping
DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scrape Dark Entries reviews")
    p.add_argument("--days", type=int, default=2, help="Days back from reference date")
    p.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    return p.parse_args()


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_dutch_date(text):
    """Parse a Dutch date string like '20 mei 2026' into a date object."""
    text = text.strip()
    m = re.match(
        r"(\d{1,2})\s+(" + "|".join(DUTCH_MONTHS.keys()) + r")\s+(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        day, month_name, year = m.groups()
        month = DUTCH_MONTHS[month_name.lower()]
        try:
            return datetime(int(year), month, int(day)).date()
        except ValueError:
            return None
    return None


def extract_artist_album(title):
    """Extract artist and album from 'Artist: Album Title' format."""
    title = title.strip()
    if ": " in title:
        parts = title.split(": ", 1)
        artist = parts[0].strip()
        album = parts[1].strip()
        album = re.sub(r"\s*\([^)]*\)\s*$", "", album).strip()
        if not artist:
            artist = ""
        if not album:
            album = title
    else:
        artist = ""
        album = title
    return artist, album


def fetch_article_body(article_url):
    """Fetch full article page and extract body text, return (body, excerpt)."""
    try:
        html = fetch(article_url)
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        # Look for main content area
        body_el = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|body|post|entry|article", re.I))
            or soup.find("div", class_=re.compile(r"tm-content|uk-container", re.I))
        )
        if not body_el:
            body_el = soup
        body = body_el.get_text(" ", strip=True)
        body = re.sub(r"\s+", " ", body).strip()
        excerpt = body[:500]
        return body, excerpt
    except Exception:
        return "", ""


def extract_card(container, seen_urls, cutoff, items):
    """Extract article data from a single article card container."""
    title_tag = container.find(["h2", "h3"], class_=re.compile(r"\bel-title\b"))
    if not title_tag:
        return False

    link = title_tag.find("a")
    if not link:
        return False

    href = link.get("href", "").strip()
    if not href:
        return False

    full_url = f"{BASE}{href}" if href.startswith("/") else href
    if not full_url.startswith("http") or full_url in seen_urls:
        return False

    if not re.match(rf"{re.escape(BASE)}/recensies/", full_url):
        seen_urls.add(full_url)
        return False

    seen_urls.add(full_url)
    article_title = link.get_text(strip=True)
    if not article_title or len(article_title) < 3:
        return False

    # --- Date ---
    pub_date = None
    meta_div = container.find("div", class_=re.compile(r"\bel-meta\b"))
    if meta_div:
        time_el = meta_div.find("time")
        if time_el:
            dt_str = time_el.get("datetime", "")
            if dt_str:
                try:
                    pub_date = datetime.fromisoformat(dt_str).date()
                except (ValueError, TypeError):
                    pass
            if pub_date is None:
                pub_date = parse_dutch_date(time_el.get_text(strip=True))

    if pub_date is None:
        time_el = container.find("time")
        if time_el:
            dt_str = time_el.get("datetime", "")
            if dt_str:
                try:
                    pub_date = datetime.fromisoformat(dt_str).date()
                except (ValueError, TypeError):
                    pass
            if pub_date is None:
                pub_date = parse_dutch_date(time_el.get_text(strip=True))

    if pub_date is None:
        sys.stderr.write(f"  No date for: {article_title[:50]}...\n")
        return False

    if pub_date < cutoff:
        return False

    # --- Fetch full article body ---
    body, excerpt = fetch_article_body(full_url)

    # Fallback excerpt from list page if body fetch failed
    if not body:
        content_div = container.find("div", class_=re.compile(r"\bel-content\b"))
        if content_div:
            excerpt = content_div.get_text(" ", strip=True)[:500]
        else:
            full_text = container.get_text(" ", strip=True)
            if article_title in full_text:
                excerpt = full_text.split(article_title, 1)[-1].strip()[:500]
        body = ""

    excerpt = excerpt[:500].replace("\n", " ").strip()

    # --- Artist / Album ---
    artist, album = extract_artist_album(article_title)
    if not album:
        album = article_title

    items.append({
        "album": album,
        "artist": artist,
        "score": None,
        "url": full_url,
        "source": "Dark Entries",
        "pub_date": pub_date.isoformat(),
        "tags": "dark,experimental,gothic-industrial",
        "excerpt": excerpt,
        "body": body,
        "site_id": "dark_entries",
        "crawl_status": "success",
        "type": "review",
    })

    sys.stderr.write(f"  OK: {article_title[:60]}... ({pub_date})\n")
    return True


def scrape_page(url, cutoff, seen_urls, items):
    """Scrape a single page for article cards."""
    try:
        html = fetch(url)
    except Exception as e:
        sys.stderr.write(f"Error fetching {url}: {e}\n")
        return False

    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_=re.compile(r"\bel-item\b"))
    sys.stderr.write(f"  Page {url}: found {len(cards)} items\n")

    found_recent = False
    for card in cards:
        if extract_card(card, seen_urls, cutoff, items):
            found_recent = True

    return found_recent


def main():
    args = parse_args()
    ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(timezone.utc).date()
    cutoff = ref_date - timedelta(days=args.days)

    items = []
    seen_urls = set()

    sys.stderr.write(f"Scraping: {RECENSIES_URL}\n")
    found_recent = scrape_page(RECENSIES_URL, cutoff, seen_urls, items)

    sys.stderr.write(f"Scraping (homepage): {HOME_URL}\n")
    scrape_page(HOME_URL, cutoff, seen_urls, items)

    if found_recent:
        page = 12
        max_pages = 3
        for _ in range(max_pages):
            page_url = f"{RECENSIES_URL}?start={page}"
            if page_url in seen_urls:
                break
            seen_urls.add(page_url)
            sys.stderr.write(f"Scraping (paginated): {page_url}\n")
            more = scrape_page(page_url, cutoff, seen_urls, items)
            if not more:
                break
            page += 12

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff.isoformat(),
        },
        "items": items,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"Dark Entries: {len(items)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
