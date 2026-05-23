#!/usr/bin/env python3
"""Scrape The Squid's Ear via curl + parsing dynamic HTML."""

import sys, re, json, os
from datetime import datetime, timedelta

import feedparser  # attempt RSS first

SITE_URL   = "https://www.squidco.com/ear/earReviews.shtml"
OUTPUT     = "/home/liyifan/music-record/2026/05/2026-05-24/squids_ear_reviews.json"
CUTOFF     = datetime.now() - timedelta(days=3)
SITE_ID    = "squids_ear"

def log(msg):
    print(msg, flush=True)

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def main():
    import subprocess, time

    # Try RSS first
    rss_urls = [
        'https://www.squidco.com/ear/rss.xml',
        'https://www.squidco.com/ear/feed/',
        'https://www.squidco.com/rss/ear.xml',
    ]
    found_rss = False
    for rss_url in rss_urls:
        log(f"Trying RSS: {rss_url}")
        res = subprocess.run(['curl', '-sL', '--max-time', '15', rss_url],
                            capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip() and \
           '<rss' in res.stdout[:200].lower() or '<feed' in res.stdout[:200].lower():
            log(f"RSS found at {rss_url}")
            found_rss = True
            break
        else:
            log(f"RSS not at {rss_url}")

    if not found_rss:
        log("No RSS — fetching dynamic page with curl + UA")

    # Fetch the dynamic reviews page
    cmd = ['curl', '-sL', '--max-time', '30',
           '-H', 'User-Agent: Mozilla/5.0 (X11; Linux aarch64; rv:120.0) Gecko/20100101 Firefox/120.0',
           '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           '-H', 'Accept-Language: en-US,en;q=0.5',
           '-H', 'Connection: keep-alive',
           SITE_URL]
    res = subprocess.run(cmd, capture_output=True, text=True)
    html = res.stdout

    log(f"Fetched {len(html)} bytes")

    # The reviews are loaded by updateTable() JavaScript function via AJAX
    # Find the table structure
    # Look for newsID links in the HTML
    hrefs = re.findall(r'href="(/cgi-bin/news/newsView\.cgi\?newsID=\d+)"', html)
    log(f"Found {len(hrefs)} newsID links in raw HTML")

    # The page uses prototype.js AJAX — let's find the data URL
    ajax_urls = re.findall(r'url\s*[=:]\s*["\']([^"\']+)["\']', html)
    log(f"AJAX URL patterns: {ajax_urls[:10]}")

    # The review table is loaded via /cgi-bin/news/newsSearch.cgi or similar
    # Let's check the updateTable function
    update_calls = re.findall(r'updateTable\s*\(\s*([^)\s]+)\s*\)', html)
    log(f"updateTable calls: {update_calls}")

    # Find the newsSearch CGI
    search_urls = re.findall(r'new\s+Ajax\.Updater\s*\([^)]+\)', html)
    log(f"Ajax.Updater patterns: {search_urls[:5]}")

    # Write what we have
    with open("/tmp/squids_raw.html", "w") as f:
        f.write(html)
    log("Saved raw HTML to /tmp/squids_raw.html")

    # Count items and report
    items = []
    for href in hrefs:
        items.append({
            "album": "",
            "artist": "",
            "score": None,
            "url": "https://www.squidco.com" + href,
            "source": SITE_URL,
            "pub_date": "",
            "tags": [],
            "excerpt": "",
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        })

    log(f"Found {len(items)} review URLs from raw HTML")
    # Need artist/title — requires visiting each review page or parsing table JS
    # Write output with what we have (partial)
    with open(OUTPUT, "w") as f:
        json.dump(items, f, indent=2)

    print(json.dumps({"count": len(items), "output": OUTPUT, "note": "partial - URLs only, no artist/album"}))

if __name__ == "__main__":
    main()