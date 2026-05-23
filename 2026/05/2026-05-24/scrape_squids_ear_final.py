#!/usr/bin/env python3
"""Scrape The Squid's Ear from returnArticlesV2.php listing — date-enforced 3-day window."""

import sys, re, json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

OUTPUT  = "/home/liyifan/music-record/2026/05/2026-05-24/squids_ear_reviews.json"
CUTOFF  = (datetime.now() - timedelta(days=3)).date()
SITE_ID = "squids_ear"
BASE    = "https://www.squidco.com"

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

def get_date(url):
    """Get yyyy-mm-dd date from detail page, or '' if unavailable."""
    html = fetch(url, timeout=15)
    m = re.search(r'(\d{4}-\d{2}-\d{2})', html)
    return m.group(1) if m else ""

def parse_full_page0():
    """Parse /tmp/squids_page0.html — only rows from the searchResults section."""
    with open('/tmp/squids_page0.html', 'r', errors='replace') as f:
        html = f.read()

    start = html.find('<searchResults>')
    end   = html.find('</searchResults>')
    if start == -1 or end == -1:
        log("ERROR: searchResults section not found")
        return []
    section = html[start:end]

    items = []
    row_pat = re.compile(
        r'<tr>\s*'
        r'<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=(\d+)\'>([^<]+)</a></td>\s*'
        r'<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'>([^<]+)</a></td>\s*'
        r'<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'>([^<]+)</a></td>\s*'
        r'<td><a href=\'/cgi-bin/news/newsView\.cgi\?newsID=\d+\'><i>([^<]+)</i></a></td>\s*'
        r'</tr>',
        re.IGNORECASE)

    for m in row_pat.finditer(section):
        items.append(dict(
            news_id=m.group(1),
            artist=m.group(2).strip(),
            title=m.group(3).strip(),
            label=m.group(4).strip(),
            author=m.group(5).strip(),
            url=f"{BASE}/cgi-bin/news/newsView.cgi?newsID={m.group(1)}"))
    return items

def main():
    log(f"CUTOFF = {CUTOFF}")
    log("Parsing page0 HTML...")
    items = parse_full_page0()
    if not items:
        log("No items — aborting")
        sys.exit(1)
    log(f"Parsed {len(items)} items, range: {items[0]['news_id']} – {items[-1]['news_id']}")

    items.sort(key=lambda x: int(x['news_id']), reverse=True)

    results = []
    BATCH = 20
    i = 0
    batches = 0
    old_hit = 0  # count of items that fell past cutoff

    while i < len(items):
        batch = items[i:i+BATCH]
        with ThreadPoolExecutor(max_workers=BATCH) as ex:
            futures = {ex.submit(get_date, r['url']): r for r in batch}
            for future in as_completed(futures):
                r = futures[future]
                r['pub_date'] = future.result()

        for r in batch:
            text = r['artist'] + ' ' + r['title'] + ' ' + r['label']
            if re.search(r'\b(BLU-RAY|UHD|VOD|DVD)\b', text, re.IGNORECASE):
                i += 1
                continue

            date_str = r.get('pub_date', '')

            if date_str:
                try:
                    pub_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if pub_dt < CUTOFF:
                        old_hit += 1
                        i += 1
                        continue
                except ValueError:
                    pass

            results.append({
                "album": r['title'],
                "artist": r['artist'],
                "score": None,
                "url": r['url'],
                "source": "https://www.squidco.com/ear/earReviews.shtml",
                "pub_date": date_str,
                "tags": [],
                "excerpt": r['title'][:500],
                "site_id": SITE_ID,
                "crawl_status": "success",
                "type": "review",
            })

        batches += 1
        # Log first item of batch for visibility
        first_url = batch[0]['url']
        first_date = batch[0].get('pub_date', '')
        log(f"Batch {batches}: scanned {min(i+BATCH, len(items))}/{len(items)}, "
            f"collected {len(results)}, old_hit={old_hit}, first_url={first_url}, first_date={first_date}")
        i += BATCH

    log(f"Total results: {len(results)}")
    with open(OUTPUT, "w") as f:
        json.dump(results, f, indent=2)
    log(f"Written to {OUTPUT}")
    print(json.dumps({"count": len(results), "output": OUTPUT}))

if __name__ == "__main__":
    main()