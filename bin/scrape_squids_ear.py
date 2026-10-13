#!/usr/bin/env python3
"""
scrape_squids_ear.py — Scrape The Squid's Ear (squidsear.com) for album reviews.

URL: https://squidsear.com/cgi-bin/news/newsView.cgi?newsList=1
List page shows the most recent ~50 reviews in a sidebar. We use the
newsTrailer.cgi endpoint (max=24) for a cleaner listing with up to 24 items,
then fetch each article individually for the full body and publication date.

Outputs JSON array of review objects to stdout.
Uses curl (subprocess) + BeautifulSoup.
Filters to articles published within the last N days.

Usage:
  python3 scrape_squids_ear.py                              # last 2 days
  python3 scrape_squids_ear.py --days 7                     # last 7 days
  python3 scrape_squids_ear.py --date 2026-05-24            # specific date
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup

SITE_ID = "squids_ear"
SOURCE = "The Squid's Ear"
# 2026-08-15: 站点迁移到 squidco.com 域名下（原 squidsear.com 已失效）
# 主页 https://www.squidco.com/ear/ 受 Cloudflare 保护但 newsTrailer.cgi 可直连
BASE_URL = "https://www.squidco.com"
LIST_URL = "https://www.squidco.com/cgi-bin/news/newsTrailer.cgi?tableHTML=yes&max=24&target=homepage"
TODAY = datetime.now(timezone.utc).date()
MAX_ARTICLES = 20


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


def parse_article_date(text: str):
    """
    Parse date from article page text like '2017-12-13' (YYYY-MM-DD).
    Returns (datetime.date, str) tuple — date object and ISO string.
    """
    if not text:
        return None, ""
    text = text.strip()
    # Try YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            dt = datetime.strptime(m.group(0), "%Y-%m-%d")
            return dt.date(), dt.date().isoformat()
        except ValueError:
            pass
    # Try "Month YYYY" pattern as fallback
    m = re.search(r"([A-Z][a-z]+)\s+(\d{4})", text)
    if m:
        try:
            dt = datetime.strptime(f"01 {m.group(1)} {m.group(2)}", "%d %B %Y")
            return dt.date(), dt.date().isoformat()
        except ValueError:
            try:
                dt = datetime.strptime(f"01 {m.group(1)} {m.group(2)}", "%d %b %Y")
                return dt.date(), dt.date().isoformat()
            except ValueError:
                pass
    return None, ""


def is_recent(pub_date, cutoff):
    """Check if a date is within the cutoff window (inclusive, cutoff <= date <= today)."""
    if pub_date is None:
        return False
    return cutoff <= pub_date <= TODAY


def extract_reviews_from_list(html: str) -> list:
    """
    Parse the newsTrailer listing page for review URLs and metadata.

    Each listing item:
        <a href="...newsID=N">
            <img ...>
            <b>Artist:</b>
            Album Title
            (Label)
        </a>

    Returns list of dicts with: url, news_id, artist, album (partial).
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag.get("href", ""))
        m = re.search(r"newsID=(\d+)", href)
        if not m:
            continue
        news_id = m.group(1)

        # Build absolute URL
        if href.startswith("/"):
            url = f"{BASE_URL}{href}"
        elif href.startswith("http"):
            url = href
        else:
            url = f"{BASE_URL}/{href}"

        # Extract artist from <b> tag
        b_tag = a_tag.find("b")
        artist = ""
        if b_tag:
            artist = b_tag.get_text(strip=True).rstrip(":").strip()

        # Extract label from img alt attribute (more reliable than parsing text)
        img_tag = a_tag.find("img")
        alt_text = str(img_tag.get("alt", "")) if img_tag else ""
        # Label is in outermost parentheses at end: "... (Label)"
        # Find the last ')' then walk backwards to find matching '('
        label = ""
        if alt_text:
            last_close = alt_text.rfind(")")
            if last_close != -1:
                depth = 0
                match_open = -1
                for i in range(last_close, -1, -1):
                    if alt_text[i] == ")":
                        depth += 1
                    elif alt_text[i] == "(":
                        depth -= 1
                        if depth == 0:
                            match_open = i
                            break
                if match_open != -1:
                    label = alt_text[match_open + 1:last_close].strip()

        # Extract album by removing artist prefix and label suffix
        full_text = a_tag.get_text(" ", strip=True)
        album = full_text
        if artist and full_text.startswith(artist):
            rest = full_text[len(artist):].lstrip(": ").strip()
            if label:
                # Try to remove label with surrounding parens or without
                for variant in [f"({label})", f"( {label} )", label]:
                    if rest.endswith(variant):
                        rest = rest[:-len(variant)].strip()
                        break
            album = rest
        # Clean excessive whitespace
        album = re.sub(r"\s+", " ", album).strip()

        items.append({
            "url": url,
            "news_id": news_id,
            "artist": artist,
            "album": album,
        })

    return items


def extract_article(html: str, list_info: dict, cutoff) -> dict | None:
    """
    Parse a single Squid's Ear article page for the full review.

    Article page structure:
      - <title> tag: "Review: Artist - Album (Label)"
      - <span class="zTextLarge"> blocks for artist/album/label
      - <font size="-2"> with date in YYYY-MM-DD format
      - <div style="max-width: 90%; margin: 0 auto; text-align: left;"> with <p> tags for body

    Returns a review dict or None if date filter fails.
    """
    soup = BeautifulSoup(html, "lxml")

    # --- Date ---
    font_small = soup.find("font", attrs={"size": "-2"})
    date_text = ""
    if font_small:
        date_text = font_small.get_text(strip=True)
    pub_date_obj, pub_date = parse_article_date(date_text)

    # Filter by date cutoff
    if not is_recent(pub_date_obj, cutoff):
        return None

    # --- Title ---
    title_tag = soup.find("title")
    raw_title = title_tag.get_text(strip=True) if title_tag else ""

    # --- Body ---
    body_parts = []
    body_divs = soup.find_all("div", style=True)
    for d in body_divs:
        style = d.get("style") or ""
        if "max-width: 90%" in style and "text-align: left" in style:
            # Get all <p> text from this div
            for p in d.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    body_parts.append(text)
    body = "\n\n".join(body_parts)
    excerpt = body[:500] if body else ""

    # Use album/artist from list_info (more reliable than parsing from article)
    album = list_info.get("album", "")
    artist = list_info.get("artist", "")

    # Fallback: try to extract from title if list_info didn't have it
    if not artist and not album and raw_title:
        # "Review: Artist - Album (Label)"
        title_text = raw_title
        if title_text.startswith("Review:"):
            title_text = title_text[len("Review:"):].strip()
        for sep in (" – ", " — ", " - "):
            if sep in title_text:
                parts = title_text.split(sep, 1)
                artist = parts[0].strip()
                rest = parts[1].strip()
                # Remove trailing label in parentheses
                album = re.sub(r"\s*\([^)]*\)\s*$", "", rest).strip()
                break

    return {
        "album": album,
        "artist": artist,
        "score": None,
        "url": list_info["url"],
        "source": SOURCE,
        "pub_date": pub_date,
        "tags": "experimental,avant-garde,improvisation",
        "excerpt": excerpt,
        "body": body,
        "site_id": SITE_ID,
        "crawl_status": "success",
        "type": "review",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Squid's Ear reviews."
    )
    parser.add_argument(
        "--days",
        type=float,
        default=1.5,
        help="Number of days back to include (default: 2)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Specific date YYYY-MM-DD to filter reviews (overrides --days)",
    )
    args = parser.parse_args()

    if args.date:
        try:
            cutoff = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.stderr.write(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        cutoff = TODAY - timedelta(days=args.days)

    sys.stderr.write(f"Squid's Ear scraper — Today: {TODAY}, Cutoff: {cutoff}\n")

    # Step 1: Fetch the listing page
    html = fetch(LIST_URL)
    if not html:
        sys.stderr.write("ERROR: Failed to fetch listing page\n")
        print(json.dumps([]))
        sys.exit(1)

    list_items = extract_reviews_from_list(html)
    sys.stderr.write(f"Found {len(list_items)} items on listing page\n")

    # Limit to MAX_ARTICLES
    list_items = list_items[:MAX_ARTICLES]
    sys.stderr.write(f"Processing top {len(list_items)} articles\n")

    # Step 2: Fetch each article and extract full data
    all_reviews = []
    seen_urls = set()

    for idx, item in enumerate(list_items, 1):
        article_html = fetch(item["url"])
        if not article_html:
            sys.stderr.write(f"  [{idx}/{len(list_items)}] SKIP — failed to fetch {item['url']}\n")
            continue

        review = extract_article(article_html, item, cutoff)
        if review is None:
            sys.stderr.write(f"  [{idx}/{len(list_items)}] SKIP — date out of range: {item['url']}\n")
            continue

        if review["url"] not in seen_urls:
            seen_urls.add(review["url"])
            all_reviews.append(review)
            sys.stderr.write(
                f"  [{idx}/{len(list_items)}] OK — {review['artist']} - {review['album']} "
                f"({review['pub_date']})\n"
            )

        # Be polite between article fetches
        import time
        time.sleep(0.5)

    # Output as JSON array
    print(json.dumps(all_reviews, indent=2, ensure_ascii=False))
    sys.stderr.write(f"Total: {len(all_reviews)} reviews written to stdout\n")


if __name__ == "__main__":
    main()
