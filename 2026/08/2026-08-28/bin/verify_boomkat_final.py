#!/usr/bin/env python3
"""Final acceptance check for boomkat_reviews.json against the task spec."""
import json
from collections import Counter
from datetime import datetime, timezone

REQUIRED = ["album", "artist", "score", "url", "source", "pub_date", "tags",
            "excerpt", "body", "site_id", "crawl_status", "type"]

d = json.load(open("boomkat_reviews.json"))
ok = True

# wrapper shape
assert set(d.keys()) >= {"meta", "items"}, "missing meta/items wrapper"
it = d["items"]
print("wrapper: {meta, items} OK; items =", len(it))
print("meta:", json.dumps(d["meta"], ensure_ascii=False))

# required fields present on every item
for n, i in enumerate(it):
    missing = [f for f in REQUIRED if f not in i]
    if missing:
        ok = False
        print(f"  item {n} missing {missing}")
print("required fields: OK" if ok else "required fields: FAIL")

# body non-empty everywhere
empty = [n for n, i in enumerate(it) if not (i.get("body") or "").strip()]
print("empty bodies:", len(empty), "OK" if not empty else empty[:10])

# no cart-widget contamination left
cart = [n for n, i in enumerate(it)
        if "Add to crate" in (i.get("body") or "")
        or "Play All MP3" in (i.get("body") or "")]
print("cart-junk bodies:", len(cart), "OK" if not cart else cart[:10])

# types valid
print("types:", Counter(i["type"] for i in it))
bad_type = [n for n, i in enumerate(it)
            if i["type"] not in ("review", "feature", "tracklist")]
print("invalid types:", bad_type or "none")

# 36h window: cutoff 2026-08-26
dates = Counter(i.get("pub_date") for i in it)
print("pub_date distribution:", dict(dates))
stale = [n for n, i in enumerate(it) if (i.get("pub_date") or "") < "2026-08-26"]
print("outside 36h window:", stale or "none")

# non-music filter
nm = [i["album"] for i in it
      if any(m in f"{i['album']} {i['artist']}".upper()
             for m in ("(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)"))]
print("non-music leftovers:", nm or "none")

# score is null (Boomkat has no numeric ratings)
print("scores:", Counter(str(i.get("score")) for i in it))

# body length stats
lens = sorted(len(i["body"]) for i in it)
print("body len min/median/max:", lens[0], lens[len(lens) // 2], lens[-1])
print("reviews with >=500 char body:",
      sum(1 for i in it if i["type"] == "review" and len(i["body"]) >= 500))
