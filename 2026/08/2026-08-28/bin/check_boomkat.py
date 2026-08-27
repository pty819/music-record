#!/usr/bin/env python3
"""Integrity check for boomkat_reviews.json."""
import json
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "boomkat_reviews.json"
d = json.load(open(path))
print("meta:", json.dumps(d.get("meta"), ensure_ascii=False))
it = d.get("items", [])
print("items:", len(it))
empty = [i for i in it if not (i.get("body") or "").strip()]
print("empty_bodies:", len(empty))
print("crawl_status:", Counter(i.get("crawl_status") for i in it))
print("type:", Counter(i.get("type") for i in it))
if it:
    print("keys:", sorted(it[0].keys()))
    print("body_lens_first10:", [len(i.get("body") or "") for i in it[:10]])
for i in empty[:8]:
    print("  EMPTY:", i.get("url"))
