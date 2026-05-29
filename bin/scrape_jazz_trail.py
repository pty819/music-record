#!/usr/bin/env python3
"""
scrape_jazz_trail.py — Scrape Jazz Trail blog (jazztrail.net) for album reviews.
Fetches list page(s), then visits each article for full body text.
Outputs standardized JSON with excerpt + body fields.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

SITE_ID = "jazz_trail"
SOURCE = "JazzTrail"
BASE_URL = "https://www.jazztrail.net"
LIST_URL = f"{BASE_URL}/blog"


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scrape Jazz Trail blog reviews")
    p.add_argument("--days", type=float, default=1.5, help="Days back from reference date")
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


def parse_date(time_el) -> tuple:
    """
    Parse date from a <time> element.
    Returns (date_obj, iso_string) tuple.
    """
    datetime_attr = time_el.get("datetime", "")
    if datetime_attr:
        try:
            dt = datetime.strptime(datetime_attr[:10], "%Y-%m-%d")
            return dt.date(), dt.date().isoformat()
        except ValueError:
            pass

    text = time_el.get_text(strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        for fmt in ("%B %d, %Y", "%B %d %Y"):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.date(), dt.date().isoformat()
            except ValueError:
                continue
    return None, ""


def is_recent(pub_date, cutoff):
    """Check if a date is within the cutoff window (inclusive, cutoff <= date <= today)."""
    if pub_date is None:
        return False
    return cutoff <= pub_date


def fetch_article_body(article_url):
    """Fetch full article page and extract body text, return (body, excerpt)."""
    try:
        html = fetch(article_url)
        if not html:
            return "", ""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        # SquareSpace: entry-content body
        body_el = (
            soup.find("div", class_="entry-content")
            or soup.find("div", class_=re.compile(r"body entry-content|sqs-html-content|post-body", re.I))
            or soup.find("article")
            or soup.find("main")
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
    """Parse review items from a Jazz Trail blog listing HTML page."""
    soup = BeautifulSoup(html, "lxml")
    reviews = []

    for article in soup.find_all("article", class_="hentry"):
        # --- Title + URL ---
        title_el = article.find("h1", class_="entry-title")
        if not title_el:
            continue

        link_el = title_el.find("a", href=True, attrs={"data-content-field": "title"})
        if not link_el:
            link_el = title_el.find("a", href=True)
        if not link_el:
            continue

        raw_title = link_el.get_text(strip=True)
        href = str(link_el.get("href", ""))

        if href.startswith("/"):
            url = f"{BASE_URL}{href}"
        elif href.startswith("http"):
            url = href
        else:
            url = f"{BASE_URL}/{href}"

        # --- Date ---
        time_el = article.find("time", class_="published")
        if not time_el:
            time_el = article.find("time")
        if not time_el:
            continue

        pub_date_obj, pub_date = parse_date(time_el)
        if not is_recent(pub_date_obj, cutoff):
            continue

        # --- Split title into artist and album ---
        artist = ""
        album = raw_title
        for sep in (" – ", " — ", " - "):
            if sep in raw_title:
                parts = raw_title.split(sep, 1)
                artist = parts[0].strip()
                album = parts[1].strip()
                break

        # --- Fetch full article body ---
        body, excerpt = fetch_article_body(url)

        # Fallback excerpt from listing page if body fetch failed
        if not body:
            text = article.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            excerpt = text[:500]
            body = ""

        reviews.append({
            "album": album.strip() if album else raw_title,
            "artist": artist,
            "score": None,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": "jazz,avant-garde,improvisation",
            "excerpt": excerpt[:500],
            "body": body,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        })

    return reviews


def get_next_page_url(html: str) -> str | None:
    """Get the URL for the next (older) page of blog posts, if any."""
    soup = BeautifulSoup(html, "lxml")
    older_link = soup.find("a", class_="older-posts")
    if older_link and older_link.get("href"):
        href = str(older_link.get("href", ""))
        if href.startswith("/"):
            return f"{BASE_URL}{href}"
        elif href.startswith("http"):
            return href
        else:
            return f"{BASE_URL}/{href}"
    return None


def main():
    args = parse_args()
    ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(timezone.utc).date()
    cutoff = ref_date - timedelta(days=args.days)

    sys.stderr.write(f"JazzTrail scraper — Ref date: {ref_date}, Cutoff: {cutoff}\n")

    all_reviews = []
    seen_urls = set()
    next_url = LIST_URL
    page_num = 0

    while next_url:
        page_num += 1
        html = fetch(next_url)
        if not html:
            sys.stderr.write(f"ERROR: Failed to fetch page {page_num}: {next_url}\n")
            break

        reviews = extract_reviews_from_html(html, cutoff)
        new_count = 0
        for r in reviews:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_reviews.append(r)
                new_count += 1

        sys.stderr.write(f"  Page {page_num}: {new_count} new reviews\n")

        # Check next page — continue if we got any reviews (more might be within cutoff)
        next_url = get_next_page_url(html)
        if next_url:
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
    sys.stderr.write(f"JazzTrail: {len(all_reviews)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
