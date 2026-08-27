#!/usr/bin/env python3
"""Dump a few boomkat items in full for inspection."""
import json
import sys

path = "boomkat_reviews.json"
d = json.load(open(path))
it = d["items"]
idxs = [int(x) for x in sys.argv[1:]] or [0, 1, 50, 98]
for n in idxs:
    i = it[n]
    print("=" * 60, n)
    for k in ("album", "artist", "score", "url", "source", "pub_date", "tags",
              "site_id", "crawl_status", "type"):
        print(f"{k}: {i.get(k)!r}")
    print("excerpt:", (i.get("excerpt") or "")[:200])
    print("body[:400]:", (i.get("body") or "")[:400])
print()
print("non-music candidates:")
for i in it:
    t = (i.get("album") or "") + " " + (i.get("artist") or "")
    for bad in ("(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)", "BLU-RAY", "DVD"):
        if bad in t.upper():
            print("  ", bad, "->", i.get("album"), "/", i.get("url"))
            break
print()
print("pub_dates:", sorted({i.get("pub_date") for i in it}))
print("scores:", sorted({str(i.get("score")) for i in it})[:20])
