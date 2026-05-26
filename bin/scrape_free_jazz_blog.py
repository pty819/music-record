#!/usr/bin/env python3
"""
scrape_free_jazz_blog.py — Scrape Free Jazz Blog (freejazzblog.org)
Fetches homepage, then visits each article for full body text.
Outputs standardized JSON with excerpt + body fields.
"""
import json
import re
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

BASE_URL = "https://www.freejazzblog.org"


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scrape Free Jazz Blog posts")
    p.add_argument("--days", type=int, default=2, help="Days back from reference date")
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


def parse_date_display(text):
    """Parse 'Sunday, May 24, 2026' format."""
    text = text.strip()
    for fmt in ["%A, %B %d, %Y", "%B %d, %Y"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def classify_post(title):
    """Determine if a post is 'review' or 'feature'."""
    title_lower = title.lower()
    if "album review" in title_lower or title_lower.startswith("review:"):
        return "review"
    if " – " in title or " — " in title:
        return "review"
    if " - " in title:
        if re.search(r"\([^)]*\d{4}\)", title):
            return "review"
        return "review"
    return "feature"


def split_artist_album(title):
    """Split title into artist and album on ' – ', ' — ', or ' - '."""
    for sep in [" – ", " — ", " - "]:
        if sep in title:
            parts = title.split(sep, 1)
            artist = parts[0].strip()
            album = parts[1].strip()
            album = re.sub(r"\s*\([^)]*\)\s*$", "", album).strip()
            return artist, album
    return "", title


def fetch_article_body(article_url):
    """Fetch full article page and extract body text, return (body, excerpt)."""
    try:
        html = fetch(article_url)
        if not html:
            return "", ""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        # Blogger post body
        body_el = (
            soup.find("div", class_="post-body entry-content")
            or soup.find("div", class_=re.compile(r"post-body|entry-content", re.I))
            or soup.find("article")
            or soup.find("main")
        )
        if not body_el:
            body_el = soup
        text = body_el.get_text(" ", strip=True)
        # Remove "By AuthorName" prefix
        text = re.sub(r"^By\s+\S+(?:\s+\S+)?\s*", "", text).strip()
        body = re.sub(r"\s+", " ", text).strip()
        excerpt = body[:500]
        return body, excerpt
    except Exception:
        return "", ""


def main():
    args = parse_args()
    ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(timezone.utc).date()
    cutoff = ref_date - timedelta(days=args.days)

    html = fetch(BASE_URL)
    if not html:
        sys.stderr.write("ERROR: Failed to fetch homepage\n")
        sys.exit(1)

    soup = BeautifulSoup(html, "lxml")
    items = []
    seen_urls = set()

    post_containers = soup.find_all("div", class_="post-outer")

    for container in post_containers:
        # Date from date-header
        date_outer = container.find_parent("div", class_="date-outer")
        pub_date = None
        if date_outer:
            date_header = date_outer.find("h2", class_="date-header")
            if date_header:
                date_span = date_header.find("span")
                if date_span:
                    pub_date = parse_date_display(date_span.get_text(strip=True))

        if not pub_date:
            meta_date_el = container.find("span", class_="meta_date")
            if meta_date_el:
                pub_date = parse_date_display(meta_date_el.get_text(strip=True))

        # Title and link
        title_el = container.find("h3", class_="post-title entry-title")
        if not title_el:
            continue
        link = title_el.find("a")
        if not link:
            continue

        title = link.get_text(strip=True)
        url = str(link.get("href", "") or "")
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = BASE_URL + url
        if not url.startswith("http"):
            continue

        # Filter to dated posts (current year)
        if not re.search(r"/2026/\d{2}/", url):
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        if pub_date is None or pub_date < cutoff:
            continue

        # Fetch full article body
        body, excerpt = fetch_article_body(url)

        # Fallback excerpt from homepage if body fetch failed
        if not body:
            post_body = container.find("div", class_="post-body entry-content")
            if post_body:
                text = post_body.get_text(" ", strip=True)
                text = re.sub(r"^By\s+\S+(?:\s+\S+)?\s*", "", text).strip()
                excerpt = text[:500]
                body = ""

        # Get categories/labels
        labels = []
        meta_cats = container.find("span", class_="meta_categories")
        if meta_cats:
            for a in meta_cats.find_all("a"):
                labels.append(a.get_text(strip=True))
        post_labels = container.find("span", class_="post-labels")
        if post_labels:
            for a in post_labels.find_all("a"):
                lbl = a.get_text(strip=True)
                if lbl not in labels:
                    labels.append(lbl)

        tags_str = ",".join(labels) if labels else "free jazz,avant-garde,improvisation"
        post_type = classify_post(title)
        artist, album = split_artist_album(title)

        items.append({
            "album": album if album else title,
            "artist": artist,
            "score": None,
            "url": url,
            "source": "Free Jazz Blog",
            "pub_date": pub_date.isoformat(),
            "tags": tags_str,
            "excerpt": excerpt,
            "body": body,
            "site_id": "free_jazz_blog",
            "crawl_status": "success",
            "type": post_type,
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
    sys.stderr.write(f"FreeJazzBlog: {len(items)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
