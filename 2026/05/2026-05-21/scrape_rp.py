#!/usr/bin/env python3
"""Scrape Rhythm Passport via Camoufox REST API."""
import json, re, sys
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE = "http://127.0.0.1:9377"

def api(path, data=None, method=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    if method:
        req.get_method = lambda: method
    try:
        with urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"API error {path}: {e}", file=sys.stderr)
        return None

def main():
    three_days_ago = datetime.now() - timedelta(days=3)
    print(f"Three days ago: {three_days_ago.date()}", file=sys.stderr)

    # Create a new tab
    tab = api("/tabs", {"userId": "rp_scraper", "sessionKey": "rp", "url": "https://rhythmpassport.com/"})
    if not tab:
        print("Failed to create tab", file=sys.stderr)
        sys.exit(1)
    tid = tab["tabId"]
    print(f"Tab created: {tid}", file=sys.stderr)

    try:
        # Wait for page load
        import time; time.sleep(3)

        # Get snapshot
        snap = api(f"/tabs/{tid}/snapshot")
        if not snap:
            print("Failed to get snapshot", file=sys.stderr)
            sys.exit(1)

        print(f"Page title: {snap.get('title','')}", file=sys.stderr)
        content = snap.get("snapshot", "")
        print(f"Snapshot length: {len(content)}", file=sys.stderr)
        print(content[:3000], file=sys.stderr)

    finally:
        api(f"/tabs/{tid}", method="DELETE")

if __name__ == "__main__":
    main()