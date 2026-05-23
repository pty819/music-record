#!/usr/bin/env python3
"""Scrape The Squid's Ear via AJAX endpoint + detail page date extraction."""

import sys, re, json, os, time
from datetime import datetime, timedelta

SITE_URL   = "https://www.squidco.com/ear/earReviews.shtml"
OUTPUT     = "/home/liyifan/music-record/2026/05/2026-05-24/squids_ear_reviews.json"
CUTOFF     = datetime.now() - timedelta(days=3)
SITE_ID    = "squids_ear"
BASE       = "https://www.squidco.com"
PAGES      = 2   # only 2 pages per constraint

def log(msg):
    print(msg, flush=True)

def fetch(url, timeout=20):
    import subprocess
    res = subprocess.run(
        ['curl', '-sL', '--max-time', str(timeout),
         '-H', 'User-Agent: Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
         '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
         '-H', 'Accept-Language: en-US,en;q=0.5',
         url],
        capture_output=True, text=True)
    return res.stdout

def parse_table_page(html):
    """Extract rows from the AJAX HTML table page."""
    items = []
    # Each row: <tr><td><a href=newsID>N</a></td><td><a href=newsID>Title</a></td>...
    # Pattern: artist td has first <a>, title td has second <a>, label td has third <a>, author td has fourth <a>
    row_pat = re.compile(
        r'<tr>\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=(\d+)\'>([^<]+)</a></td>'
        r'\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'>([^<]+)</a></td>'
        r'\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'>([^<]+)</a></td>'
        r'\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'><i>([^<]+)</i></a></td>'
        r'\s*</tr>',
        re.IGNORECASE)
    for m in row_pat.finditer(html):
        news_id  = m.group(1)
        artist   = m.group(2).strip()
        title    = m.group(3).strip()
        label    = m.group(4).strip()
        author   = m.group(5).strip()
        url      = f"{BASE}/cgi-bin/news/newsView.cgi?newsID={news_id}"
        items.append({
            "news_id": news_id,
            "artist": artist,
            "title": title,
            "label": label,
            "author": author,
            "url": url,
        })
    return items

def get_date_from_detail(url):
    """Fetch detail page, extract yyyy-mm-dd date."""
    html = fetch(url, timeout=15)
    m = re.search(r'(\d{4}-\d{2}-\d{2})', html)
    if m:
        return m.group(1)
    return ""

def main():
    all_rows = []

    # Fetch up to 2 pages from AJAX endpoint
    for page_idx in range(PAGES):
        start = page_idx * 100
        api_url = f"https://www.squidco.com/ear/returnArticlesV2.php?start={start}"
        log(f"Fetching page {page_idx+1}: {api_url}")
        html = fetch(api_url)
        rows = parse_table_page(html)
        log(f"  Found {len(rows)} rows")
        all_rows.extend(rows)
        time.sleep(0.5)

    log(f"Total rows collected: {len(all_rows)}")

    # De-duplicate by news_id
    seen = {}
    for row in all_rows:
        nid = row['news_id']
        if nid not in seen:
            seen[nid] = row
        else:
            # merge: keep first
            pass
    all_rows = list(seen.values())
    log(f"After dedup: {len(all_rows)}")

    results = []
    skipped_nonmusic = 0
    skipped_old = 0

    for row in all_rows:
        # Non-music filter
        text = row['artist'] + ' ' + row['title'] + ' ' + row['label']
        if re.search(r'\b(BLU-RAY|UHD|VOD|DVD)\b', text, re.IGNORECASE):
            skipped_nonmusic += 1
            continue

        # Get date from detail page
        date_str = get_date_from_detail(row['url'])
        if not date_str:
            # Try to parse from HTML of listing page (none there) — skip if no date
            date_str = ""

        # Date filter
        if date_str:
            try:
                pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
                if pub_dt < CUTOFF:
                    skipped_old += 1
                    continue
            except ValueError:
                pass

        excerpt = row['title'][:500]

        results.append({
            "album": row['title'],
            "artist": row['artist'],
            "score": None,
            "url": row['url'],
            "source": SITE_URL,
            "pub_date": date_str,
            "tags": [],
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        })

        if len(results) % 10 == 0:
            log(f"  Processed {len(results)} / {len(all_rows)}")

    log(f"Results: {len(results)}, skipped non-music: {skipped_nonmusic}, skipped old: {skipped_old}")

    with open(OUTPUT, "w") as f:
        json.dump(results, f, indent=2)

    log(f"Written {len(results)} items to {OUTPUT}")
    print(json.dumps({"count": len(results), "output": OUTPUT}))

if __name__ == "__main__":
    main()