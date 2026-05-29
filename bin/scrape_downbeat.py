#!/usr/bin/env python3
"""
scrape_downbeat.py — Scraper for DownBeat reviews (downbeat.com)

Strategy:
  1. Try curl (urllib) on https://downbeat.com/reviews first.
     The /reviews page is server-rendered HTML (NOT JS-heavy).
  2. Fall back to Camoufox API (http://127.0.0.1:9377) if curl fails.
  3. Pages paginate via /reviews/P{offset} links inside <ul.category-list>.
  4. Extract: album, artist, reviewer, excerpt, date, rating (★ 1-5).
  5. Fetch full article body from each review's individual page.
  6. Output JSON filtered to last N days.

Output fields:
  album, artist, score (1-5), url, source='DownBeat', pub_date,
  tags='jazz,blues', excerpt, body, site_id='downbeat',
  crawl_status='success', type='review'

Usage:
  python3 scrape_downbeat.py                                 # last 2 days
  python3 scrape_downbeat.py --days 7                        # last 7 days
  python3 scrape_downbeat.py --date 2026-05-24               # specific date
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape

from bs4 import BeautifulSoup, Comment

# ── Configuration ───────────────────────────────────────────────────
BASE_URL = "https://downbeat.com"
REVIEWS_URL = f"{BASE_URL}/reviews"
CAMOFOX_URL = "http://127.0.0.1:9377"
TODAY = datetime.now(timezone.utc).date()

REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Star rating conversion ──────────────────────────────────────────
STAR_WEIGHTS = {
    "fa-star": 1.0,
    "fa-star-half": 0.5,
    "fa-star-empty": 0.0,
}


def parse_stars(star_html):
    """Parse a <span class="font_awesome_star_rank"> block into a 1-5 float."""
    if not star_html:
        return None
    score = 0.0
    for i_tag in star_html.find_all("i", class_=re.compile(r"fa-star")):
        for cls in i_tag.get("class", []):
            w = STAR_WEIGHTS.get(cls)
            if w is not None:
                score += w
                break
    return score if score > 0 else None


# ── Date parsing ────────────────────────────────────────────────────
MONTH_NAMES = {
    "january": 1, "february": 1, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_number(s):
    s = s.strip().lower()
    return MONTH_NAMES.get(s) or MONTH_ABBR.get(s[:3])


def parse_date(text):
    """Parse a date string into a datetime.date or None.

    Handles formats:
      "Apr 18, 2026 5:46 PM"
      "Published January 2026"
    """
    text = text.strip()

    # "Apr 18, 2026 ..."
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", text)
    if m:
        mon = _month_number(m.group(1))
        if mon:
            try:
                return datetime(int(m.group(3)), mon, int(m.group(2))).date()
            except ValueError:
                pass

    # "Published January 2026" — use 1st of month
    m = re.match(r"(?:Published\s+)?([A-Za-z]+)\s+(\d{4})", text)
    if m:
        mon = _month_number(m.group(1))
        if mon:
            try:
                return datetime(int(m.group(2)), mon, 1).date()
            except ValueError:
                pass

    return None


# ── HTML fetch ──────────────────────────────────────────────────────
def fetch_curl(url):
    """Fetch via urllib (curl equivalent). Returns HTML string."""
    req = urllib.request.Request(url, headers=REQ_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_camoufox(url):
    """Fetch page HTML via Camoufox headless browser API. Returns HTML or None."""
    import http.client
    import time

    # Create tab
    body = json.dumps({"userId": "downbeat", "sessionKey": "downbeat", "url": url}).encode()
    conn = http.client.HTTPConnection("127.0.0.1", 9377, timeout=30)
    try:
        conn.request("POST", "/tabs", body, {"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
    except Exception as e:
        sys.stderr.write(f"[downbeat] Camoufox create tab error: {e}\n")
        return None

    tab_id = data.get("tabId")
    if not tab_id:
        return None

    try:
        time.sleep(3)  # Let JS render
        expr = "document.documentElement.outerHTML"
        eval_body = json.dumps({"expression": expr}).encode()
        conn2 = http.client.HTTPConnection("127.0.0.1", 9377, timeout=30)
        conn2.request("POST", f"/tabs/{tab_id}/evaluate", eval_body, {"Content-Type": "application/json"})
        resp2 = conn2.getresponse()
        result = json.loads(resp2.read())
        conn2.close()
        return result.get("result")
    except Exception as e:
        sys.stderr.write(f"[downbeat] Camoufox evaluate error: {e}\n")
        return None
    finally:
        # Clean up tab
        try:
            conn3 = http.client.HTTPConnection("127.0.0.1", 9377, timeout=10)
            conn3.request("DELETE", f"/tabs/{tab_id}")
            conn3.getresponse()
            conn3.close()
        except Exception:
            pass


def fetch_page(url):
    """Try curl first, fall back to Camoufox API."""
    try:
        return fetch_curl(url)
    except Exception as e:
        sys.stderr.write(f"[downbeat] curl failed for {url}: {e}\n")
        sys.stderr.write("[downbeat] Falling back to Camoufox API...\n")
        return fetch_camoufox(url)


# ── Full article body fetch ─────────────────────────────────────────
def fetch_full_body(url: str) -> str:
    """
    Fetch a DownBeat review article page and extract the full review body.

    The article page has the main content in <div class="review-content"> or
    within <div class="body-text">. Falls back to fetching any
    substantial <p> text inside the main column.
    """
    html = fetch_page(url)
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")

    # Try various selectors for the review body
    # DownBeat article pages typically have a div with class containing "review-content"
    body_parts = []

    # Strategy 1: Look for div with review-content class
    content_div = soup.find("div", class_=re.compile(r"review-content", re.I))
    if content_div:
        for p in content_div.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                body_parts.append(text)

    # Strategy 2: Look for the main column
    if not body_parts:
        main_col = soup.find("div", class_=re.compile(r"col-sm-7"))
        if main_col:
            for p in main_col.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 50:  # Skip short labels/nav
                    body_parts.append(text)

    # Strategy 3: Generic — remove nav/header/footer and get all p text
    if not body_parts:
        for selector in ["article", ".body-text", ".entry-content", "#content"]:
            el = soup.select_one(selector)
            if el:
                for p in el.find_all("p"):
                    text = p.get_text(strip=True)
                    if text and len(text) > 50:
                        body_parts.append(text)
                if body_parts:
                    break

    return "\n\n".join(body_parts) if body_parts else ""


# ── Comment / excerpt extraction ─────────────────────────────────────
def extract_comment_date_excerpt(comment_str):
    """Parse an HTML comment block for date and review excerpt.

    Comment structure:
      <p class="postinfo">Apr 18, 2026 5:46 PM</p>
      <a href="..."><h1>...</h1></a>
      <p>Actual review text...</p>
      <p>More text...</p>{/exp:trunchtml
    """
    pub_date = None
    excerpt = ""

    # Date from postinfo
    m = re.search(
        r'<p\s+class="postinfo">\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})',
        comment_str,
    )
    if m:
        pub_date = parse_date(m.group(1))

    # Extract review text paragraphs (skip the postinfo <p> and the <a>)
    # Find all <p>...</p> blocks that contain actual review text
    paras = re.findall(r"<p>(.*?)</p>", comment_str, re.DOTALL)
    review_paras = []
    for p in paras:
        # Skip if it's the postinfo paragraph (contains a date pattern)
        if re.search(r"[A-Za-z]+\s+\d{1,2},\s+\d{4}", p) and "PM" in p:
            continue
        text = re.sub(r"<[^>]+>", " ", p)
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        if text:
            review_paras.append(text)

    if review_paras:
        excerpt = (" ".join(review_paras))[:500]

    return pub_date, excerpt


# ── Item extraction ─────────────────────────────────────────────────
def extract_item(article_el, seen_urls):
    """Extract a single review item from an <article> element.

    Returns a dict or None if out-of-range or invalid.
    """
    # Determine heading type: h2 for featured, h1 for list entries
    h_tag = article_el.find(["h1", "h2"])
    if not h_tag:
        return None

    link = h_tag.find("a")
    if not link:
        return None

    href = link.get("href", "").strip()
    if not href:
        return None
    if href.startswith("/"):
        href = BASE_URL + href
    if not href.startswith("http"):
        return None

    if href in seen_urls:
        return None
    seen_urls.add(href)

    artist = link.get_text(strip=True)
    if not artist or len(artist) < 2:
        return None

    # Album title
    album = ""
    subhead = article_el.find("subhead")
    if subhead:
        album = unescape(subhead.get_text(" ", strip=True))

    # Label (optional — inside <h6>)
    label_el = article_el.find("h6")
    label = unescape(label_el.get_text(" ", strip=True)) if label_el else ""

    # Star rating
    star_span = article_el.find("span", class_=re.compile(r"font_awesome_star_rank"))
    score = parse_stars(star_span)

    # Date and excerpt from HTML comments
    pub_date = None
    excerpt = ""

    for node in article_el.find_all(string=lambda s: isinstance(s, Comment)):
        c = node.strip()
        if not c:
            continue
        date_cand, excerpt_cand = extract_comment_date_excerpt(c)
        if date_cand and not pub_date:
            pub_date = date_cand
        if excerpt_cand and not excerpt:
            excerpt = excerpt_cand

    # Fallback: visible postinfo for date (month/year only)
    if not pub_date:
        postinfo = article_el.find("p", class_="postinfo")
        if postinfo:
            dt_text = re.sub(r"By\s*", "", postinfo.get_text(strip=True)).strip()
            pub_date = parse_date(dt_text)

    if not pub_date:
        sys.stderr.write(f"  [downbeat] No date for: {artist} - {album}\n")
        return None

    # Reviewer (not reliably available — try to parse from postinfo)
    reviewer = ""
    postinfo = article_el.find("p", class_="postinfo")
    if postinfo:
        # Check for <a> inside postinfo containing name
        a_tag = postinfo.find("a")
        if a_tag and a_tag.get_text(strip=True):
            reviewer = a_tag.get_text(strip=True)

    if not album:
        album = "[Unknown]"

    return {
        "album": album,
        "artist": artist,
        "reviewer": reviewer,
        "score": score,
        "url": href,
        "source": "DownBeat",
        "pub_date": pub_date.isoformat(),
        "tags": "jazz,blues",
        "excerpt": excerpt,
        "body": None,  # Will be filled in after fetching article page
        "site_id": "downbeat",
        "crawl_status": "success",
        "type": "review",
    }


# ── Page parsing ────────────────────────────────────────────────────
def parse_page(html, seen_urls, cutoff):
    """Parse the /reviews HTML page. Returns (items, next_page_url_or_None)."""
    soup = BeautifulSoup(html, "lxml")
    items = []

    main_col = soup.find("div", class_=re.compile(r"col-sm-7 col-sm-push-2"))
    if not main_col:
        sys.stderr.write("[downbeat] Could not find main content column\n")
        return items, None

    # ── Layout A: Featured entry ──
    featured_div = main_col.find("div", class_=re.compile(r"pad-btm-md"))
    if featured_div:
        featured_article = featured_div.find("article", class_=re.compile(r"col-sm-7"))
        if featured_article and featured_article.find("h2"):
            item = extract_item(featured_article, seen_urls)
            if item:
                # Check cutoff
                date_obj = parse_date(item["pub_date"].replace("T", " ")) if item["pub_date"] else None
                if date_obj is None:
                    date_obj = datetime.fromisoformat(item["pub_date"]).date() if item["pub_date"] else None
                if date_obj and cutoff <= date_obj <= TODAY:
                    items.append(item)
                else:
                    sys.stderr.write(f"  [downbeat] SKIP — date {item['pub_date']} out of range: {item['artist']}\n")

    # ── Layout B: List entries inside <ul class="category-list"> ──
    cat_ul = main_col.find("ul", class_=re.compile(r"category-list"))
    if cat_ul:
        for li in cat_ul.find_all("li", recursive=False):
            article = li.find("article")
            if not article:
                continue
            if not article.find("h1"):
                continue
            item = extract_item(article, seen_urls)
            if item:
                # Check cutoff
                date_obj = parse_date(item["pub_date"].replace("T", " ")) if item["pub_date"] else None
                if date_obj is None:
                    date_obj = datetime.fromisoformat(item["pub_date"]).date() if item["pub_date"] else None
                if date_obj and cutoff <= date_obj <= TODAY:
                    items.append(item)
                else:
                    sys.stderr.write(f"  [downbeat] SKIP — date {item['pub_date']} out of range: {item['artist']}\n")

    # ── Pagination ──
    next_url = None
    if cat_ul:
        # Find the pagination <p> inside category-list (last <p> child)
        pagination_p = None
        for p_tag in cat_ul.find_all("p"):
            text = p_tag.get_text(strip=True)
            if text.startswith("Page") and "of" in text:
                pagination_p = p_tag
                break
        if pagination_p:
            current_strong = pagination_p.find("strong")
            if current_strong:
                next_link = current_strong.find_next_sibling("a")
                if next_link:
                    href = (next_link.get("href") or "").strip()
                    if href:
                        next_url = href if href.startswith("http") else BASE_URL + href

    return items, next_url


# ── Main ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Scrape DownBeat reviews."
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

    seen = set()
    all_items = []
    url = REVIEWS_URL
    max_pages = 10

    sys.stderr.write(f"[downbeat] Cutoff date: {cutoff.isoformat()}\n")

    for page_num in range(1, max_pages + 1):
        sys.stderr.write(f"[downbeat] Page {page_num}: {url}\n")
        html = fetch_page(url)
        if not html:
            sys.stderr.write(f"[downbeat] Failed to fetch {url}\n")
            break

        items, next_url = parse_page(html, seen, cutoff)
        all_items.extend(items)
        sys.stderr.write(f"  → {len(items)} recent items\n")

        if not next_url:
            sys.stderr.write("[downbeat] No more pages\n")
            break

        url = next_url

        # Early stop: if we found nothing for 2 consecutive pages past page 2,
        # remaining pages are certainly older than cutoff
        if not items and page_num >= 3:
            sys.stderr.write("[downbeat] No recent items for 2+ pages, stopping\n")
            break

    # Step 2: Fetch full article body for each item
    sys.stderr.write(f"[downbeat] Fetching full article bodies for {len(all_items)} items...\n")
    for idx, item in enumerate(all_items, 1):
        sys.stderr.write(f"  [{idx}/{len(all_items)}] Fetching body: {item['url']}\n")
        body = fetch_full_body(item["url"])
        item["body"] = body if body else ""
        if not item.get("excerpt"):
            item["excerpt"] = body[:500] if body else ""
        # Brief delay to be polite
        import time
        time.sleep(0.3)

    result = {
        "meta": {
            "total": len(all_items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        },
        "items": all_items,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"[downbeat] Total: {len(all_items)} items within last {args.days} day(s)\n")


if __name__ == "__main__":
    main()
