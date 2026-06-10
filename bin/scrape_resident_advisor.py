#!/usr/bin/env python3
"""
scrape_resident_advisor.py — Scrape Resident Advisor reviews via GraphQL API.

RA is a Next.js SPA — HTML parsing doesn't work. Their public GraphQL endpoint
at ra.co/graphql returns structured review data directly.
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

GRAPHQL_URL = "https://ra.co/graphql"
BASE = "https://ra.co"

QUERY = """{ reviews(type: ALL) {
    id title date blurb content contentUrl label recommended
    author { name }
    artists { name }
} }"""


def parse_args():
    p = argparse.ArgumentParser(description="Scrape Resident Advisor reviews")
    p.add_argument("--days", type=float, default=1.5)
    p.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    return p.parse_args()


def graphql(query):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(GRAPHQL_URL, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text).strip()


def main():
    args = parse_args()
    ref_date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                if args.date else datetime.now(timezone.utc).date())
    cutoff = ref_date - timedelta(days=args.days)

    resp = graphql(QUERY)
    reviews = resp.get("data", {}).get("reviews", [])
    print(f"RA: fetched {len(reviews)} reviews from GraphQL", file=sys.stderr)

    items = []
    for r in reviews:
        # Parse date
        raw_date = r.get("date", "")
        try:
            pub_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            pub_date = pub_dt.date()
        except (ValueError, AttributeError):
            continue

        if pub_date < cutoff:
            continue

        title = (r.get("title") or "").strip()
        label_name = (r.get("label") or "").strip()
        recommended = r.get("recommended", False)

        # Artist from title ("Artist - Album")
        artist = ""
        album = title
        if " - " in title:
            artist, album = title.split(" - ", 1)

        # Artists list
        artist_names = [a["name"] for a in (r.get("artists") or []) if a.get("name")]
        if artist_names and not artist:
            artist = ", ".join(artist_names)

        # Author
        author = ""
        if r.get("author") and r["author"].get("name"):
            author = r["author"]["name"]

        # Body / excerpt from GraphQL content field
        raw_body = r.get("content") or r.get("blurb") or ""
        body = strip_html(raw_body)
        excerpt = body[:500]

        url = f"{BASE}{r['contentUrl']}" if r.get("contentUrl") else ""

        items.append({
            "album": album.strip(),
            "artist": artist.strip(),
            "score": None,
            "url": url,
            "source": "Resident Advisor",
            "pub_date": pub_date.isoformat(),
            "tags": "electronic",
            "excerpt": excerpt,
            "body": body,
            "site_id": "resident_advisor",
            "crawl_status": "success",
            "type": "review",
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
    sys.stderr.write(f"RA: {len(items)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
