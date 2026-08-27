#!/usr/bin/env python3
"""Spot-check body quality on boomkat_reviews.json."""
import json

d = json.load(open("boomkat_reviews.json"))
items = sorted(d["items"], key=lambda i: len(i["body"]))

print("=== shortest 3 bodies ===")
for i in items[:3]:
    print(f"\n-- {i['artist']} : {i['album']} ({len(i['body'])}c)")
    print(f"  url: {i['url']}")
    print(f"  body[:220]: {i['body'][:220]!r}")

print("\n=== a longer one (mid) ===")
m = items[len(items) // 2]
print(f"-- {m['artist']} : {m['album']} ({len(m['body'])}c)")
print(f"  body[:200]: {m['body'][:200]!r}")
