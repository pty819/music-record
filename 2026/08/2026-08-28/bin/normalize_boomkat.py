#!/usr/bin/env python3
"""normalize_boomkat.py — fix field semantics on boomkat_reviews.json.

Two issues left by scrape_boomkat.py:

1. `type` was hardcoded to "feature" for every product page. Boomkat product
   pages carry editorial album reviews, so type must be "review". Items where
   the site has no editorial copy (has_review=False, set by
   fix_boomkat_bodies.py) are "tracklist" — a bare release listing.
2. `meta.total` / `meta.scraped_at` are refreshed, and meta gains the counts
   downstream scoring needs.

Boomkat publishes no numeric ratings, so `score` stays null throughout.

Usage: normalize_boomkat.py <boomkat_reviews.json>
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

NON_MUSIC = ("(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: normalize_boomkat.py <boomkat_reviews.json>")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    items = data["items"]

    # Non-music filter (task constraint): drop video formats.
    kept = []
    dropped = []
    for it in items:
        hay = f"{it.get('album','')} {it.get('artist','')}".upper()
        if any(m in hay for m in NON_MUSIC):
            dropped.append(it.get("album"))
            continue
        kept.append(it)

    reviews = tracklists = 0
    for it in kept:
        has_review = it.get("has_review")
        if has_review is None:
            # Items untouched by the fix pass had genuine prose bodies.
            has_review = bool((it.get("body") or "").strip())
        if has_review:
            it["type"] = "review"
            reviews += 1
        else:
            it["type"] = "tracklist"
            tracklists += 1
        it.setdefault("score", None)
        it["has_review"] = bool(has_review)

    data["items"] = kept
    data["meta"] = {
        "total": len(kept),
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cutoff_date": data.get("meta", {}).get("cutoff_date", "2026-08-26"),
        "hours_scanned": "36",
        "site": "boomkat",
        "reviews": reviews,
        "tracklists": tracklists,
        "dropped_non_music": len(dropped),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(json.dumps(data["meta"], indent=2))
    if dropped:
        print("dropped:", dropped)


if __name__ == "__main__":
    main()
