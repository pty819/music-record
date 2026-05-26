#!/usr/bin/env python3
"""
scrape_songlines.py — Scrape Songlines /reviews page for album reviews.
Fetches list page, then visits each review page for body text (may be paywalled).
Outputs standardized JSON with excerpt + body fields.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

SITE_ID = "songlines"
SOURCE = "Songlines"
BASE_URL = "https://songlines.co.uk"
LIST_URL = f"{BASE_URL}/reviews"


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scrape Songlines reviews")
    p.add_argument("--days", type=int, default=2, help="Days back from reference date")
    p.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    return p.parse_args()


def fetch(url: str) -> str:
    """Fetch a URL with curl, return HTML text."""
    result = subprocess.run(
        ["curl", "-sL", url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        sys.stderr.write(f"curl error {result.returncode} for {url}: {result.stderr[:200]}\n")
        return ""
    return result.stdout


def count_stars(text: str) -> int:
    """Count ★ characters in a rating string."""
    if not text:
        return 0
    return text.count("★")


def parse_issue_date(text: str):
    """
    Parse date from 'Reviewed by X in issue: Month/Year' or 'Month/Year'.
    Returns (datetime.date, str) tuple.
    """
    if not text:
        return None, ""
    m = re.search(r"in issue:\s*([A-Za-z]+)/(\d{4})", text)
    if not m:
        m = re.search(r"([A-Za-z]+)/(\d{4})", text)
    if m:
        month_str = m.group(1)
        year_str = m.group(2)
        try:
            dt = datetime.strptime(f"01 {month_str} {year_str}", "%d %B %Y")
            return dt.date(), dt.date().isoformat()
        except ValueError:
            try:
                dt = datetime.strptime(f"01 {month_str} {year_str}", "%d %b %Y")
                return dt.date(), dt.date().isoformat()
            except ValueError:
                pass
    return None, ""


def is_recent(issue_date, cutoff):
    """
    Check if an issue date is within the cutoff window.
    Month-level granularity: allow ~1.5 months around cutoff.
    """
    if issue_date is None:
        return False
    allowed_start = cutoff - timedelta(days=45)
    allowed_end = cutoff + timedelta(days=45)
    return allowed_start <= issue_date <= allowed_end


def fetch_article_body(article_url):
    """Fetch full review page and extract body text, return (body, excerpt)."""
    try:
        html = fetch(article_url)
        if not html:
            return "", ""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        # Songlines: try common content areas
        body_el = (
            soup.find("div", class_=re.compile(r"review-content|article-content|entry-content|content-body|post-content", re.I))
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


def extract_reviews_from_html(html: str, cutoff) -> list:
    """Parse review items from a Songlines reviews listing HTML page."""
    soup = BeautifulSoup(html, "lxml")
    reviews = []

    for card in soup.find_all("div", class_="review-item"):
        # --- Album name ---
        album_el = card.find("h2")
        if not album_el:
            continue
        link_el = album_el.find("a", href=True)
        if not link_el:
            continue
        album = link_el.get_text(strip=True)
        href = str(link_el.get("href", ""))

        if href.startswith("/"):
            url = f"{BASE_URL}{href}"
        elif href.startswith("http"):
            url = href
        else:
            url = f"{BASE_URL}/{href}"

        # --- Artist ---
        artist = ""
        for sibling in album_el.find_next_siblings():
            if sibling.name == "p":
                a_tag = sibling.find("a")
                if a_tag:
                    artist = a_tag.get_text(strip=True)
                    break
            elif sibling.name == "div":
                break

        # --- Rating ---
        rating_el = card.find("span", class_="rating")
        score = 0
        if rating_el:
            rating_text = rating_el.get_text(" ", strip=True)
            score = count_stars(rating_text)

        # --- Excerpt from listing ---
        excerpt_list = ""
        for p in card.find_all("p", class_="p-reviews"):
            if p.find_parent("span", class_="rating"):
                continue
            excerpt_list = p.get_text(strip=True)
            break

        # --- Date ---
        date_el = card.find("span", class_=re.compile(r"small\s*pt-2"))
        date_text = ""
        if date_el:
            date_text = date_el.get_text(" ", strip=True)
        issue_date, pub_date = parse_issue_date(date_text)

        if not is_recent(issue_date, cutoff):
            continue

        # --- Fetch full article body ---
        body, excerpt = fetch_article_body(url)

        # Fallback to listing excerpt if body fetch failed (paywall)
        if not body:
            excerpt = excerpt_list[:500]
            body = ""

        reviews.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": "world music",
            "excerpt": excerpt[:500],
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        })

    return reviews


def get_total_pages(html: str) -> int:
    """Determine total number of pages from pagination links."""
    soup = BeautifulSoup(html, "lxml")
    pages = []
    nav = soup.find("nav", attrs={"aria-label": "Page navigation"})
    if not nav:
        return 1
    for a in nav.find_all("a", class_="page-link"):
        m = re.search(r"page=(\d+)", str(a.get("href", "")))
        if m:
            pages.append(int(m.group(1)))
    return max(pages) if pages else 1


def main():
    args = parse_args()
    ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(timezone.utc).date()
    cutoff = ref_date - timedelta(days=args.days)

    sys.stderr.write(f"Songlines scraper — Ref date: {ref_date}, Cutoff: {cutoff}\n")

    all_reviews = []
    seen_urls = set()

    html = fetch(LIST_URL)
    if not html:
        sys.stderr.write("ERROR: Failed to fetch listing page\n")
        print(json.dumps({"meta": {"total": 0, "scraped_at": datetime.now(timezone.utc).isoformat(), "cutoff_date": cutoff.isoformat()}, "items": []}))
        sys.exit(1)

    total_pages = get_total_pages(html)
    sys.stderr.write(f"Found {total_pages} page(s)\n")

    for page_num in range(1, total_pages + 1):
        if page_num == 1:
            page_url = LIST_URL
            page_html = html
        else:
            page_url = f"{LIST_URL}?page={page_num}&pageSize=10"
            page_html = fetch(page_url)
            if not page_html.strip():
                continue

        reviews = extract_reviews_from_html(page_html, cutoff)
        for r in reviews:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_reviews.append(r)

        sys.stderr.write(f"  Page {page_num}: {len(reviews)} reviews\n")

        if page_num < total_pages:
            time.sleep(1)

    # Output as standardized JSON
    result = json.dumps({
        "meta": {
            "total": len(all_reviews),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff.isoformat(),
        },
        "items": all_reviews,
    }, indent=2, ensure_ascii=False)

    print(result)
    sys.stderr.write(f"Songlines: {len(all_reviews)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
