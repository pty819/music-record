#!/usr/bin/env python3
"""Scrape The Squid's Ear via AJAX endpoint — collect items within 3-day window."""

import sys, re, json, os, time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

SITE_URL   = "https://www.squidco.com/ear/earReviews.shtml"
OUTPUT     = "/home/liyifan/music-record/2026/05/2026-05-24/squids_ear_reviews.json"
CUTOFF     = datetime.now() - timedelta(days=3)
SITE_ID    = "squids_ear"
BASE       = "https://www.squidco.com"
BATCH      = 20

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
        capture_output=True, text=True, errors='replace')
    return res.stdout

def parse_table_page(html):
    items = []
    row_pat = re.compile(
        r'<tr>\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=(\d+)\'>([^<]+)</a></td>'
        r'\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'>([^<]+)</a></td>'
        r'\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'>([^<]+)</a></td>'
        r'\s*<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'><i>([^<]+)</i></a></td>'
        r'\s*</tr>',
        re.IGNORECASE)
    for m in row_pat.finditer(html):
        items.append(dict(
            news_id=m.group(1),
            artist=m.group(2).strip(),
            title=m.group(3).strip(),
            label=m.group(4).strip(),
            author=m.group(5).strip(),
            url=f"{BASE}/cgi-bin/news/newsView.cgi?newsID={m.group(1)}"))
    return items

def get_date(url):
    html = fetch(url, timeout=15)
    m = re.search(r'(\d{4}-\d{2}-\d{2})', html)
    return m.group(1) if m else ""

def main():
    log("Fetching listing page 0...")
    html = fetch("https://www.squidco.com/ear/returnArticlesV2.php?start=0")
    rows = parse_table_page(html)
    log(f"Found {len(rows)} rows, newsID range: {rows[0]['news_id']} – {rows[-1]['news_id']}")

    # Sort newest first
    rows.sort(key=lambda r: int(r['news_id']), reverse=True)

    results = []
    stop_fetching = False
    batches = 0
    i = 0

    while i < len(rows):
        batch = rows[i:i+BATCH]

        # Parallel date fetch
        with ThreadPoolExecutor(max_workers=BATCH) as ex:
            futures = {ex.submit(get_date, r['url']): r for r in batch}
            for future in as_completed(futures):
                r = futures[future]
                r['pub_date'] = future.result()

        for r in batch:
            # Non-music filter
            text = r['artist'] + ' ' + r['title'] + ' ' + r['label']
            if re.search(r'\b(BLU-RAY|UHD|VOD|DVD)\b', text, re.IGNORECASE):
                continue

            date_str = r.get('pub_date', '')

            if date_str:
                try:
                    pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if pub_dt < CUTOFF:
                        stop_fetching = True
                        # Don't add old items, but keep processing remaining rows in this batch
                        continue
                except ValueError:
                    pass

            results.append({
                "album": r['title'],
                "artist": r['artist'],
                "score": None,
                "url": r['url'],
                "source": SITE_URL,
                "pub_date": date_str,
                "tags": [],
                "excerpt": r['title'][:500],
                "site_id": SITE_ID,
                "crawl_status": "success",
                "type": "review",
            })

        batches += 1
        log(f"Batch {batches}: scanned {min(i+BATCH, len(rows))}/{len(rows)}, collected {len(results)}")
        i += BATCH

        if stop_fetching:
            log("Cutoff reached — stopping scan")
            break

    log(f"Total results: {len(results)}")
    with open(OUTPUT, "w") as f:
        json.dump(results, f, indent=2)
    log(f"Written to {OUTPUT}")
    print(json.dumps({"count": len(results), "output": OUTPUT}))

if __name__ == "__main__":
    main()