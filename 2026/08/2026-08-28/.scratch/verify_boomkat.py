#!/usr/bin/env python3
"""Verify boomkat_reviews.json structure before completing the task."""
import json, sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "boomkat_reviews.json"
d = json.load(open(path))

# wrapper check
assert isinstance(d, dict) and "meta" in d and "items" in d, "missing {meta,items} wrapper"
items = d["items"]
meta = d["meta"]

req = {"album","artist","score","url","source","pub_date","tags","excerpt","body","site_id","crawl_status","type"}
empty_body = [i for i in items if not (i.get("body") or "").strip()]
empty_excerpt = [i for i in items if not (i.get("excerpt") or "").strip()]
partial = [i for i in items if i.get("crawl_status") != "success"]
missing_fields = [i for i in items if not req.issubset(set(i.keys()))]
non_music = [i for i in items if any(x in (i.get("album","") + " " + i.get("artist","") + " " + i.get("tags","")) for x in ["(BLU-RAY)","(UHD)","(VOD)","(DVD)"])]
bad_type = [i for i in items if i.get("type") not in ("review","feature","tracklist")]

print("meta:", meta)
print("total items:", len(items))
print("empty_body:", len(empty_body), "| empty_excerpt:", len(empty_excerpt), "| partial:", len(partial))
print("missing_fields:", len(missing_fields), "| non_music:", len(non_music), "| bad_type:", len(bad_type))
print("pub_dates:", sorted(Counter(i["pub_date"] for i in items).items()))
print("types:", dict(Counter(i["type"] for i in items)))
print("all_fields_present:", not missing_fields)
print("all_have_body:", not empty_body)
print("all_have_excerpt:", not empty_excerpt)
print("all_success:", not partial)

# report errors for visibility
for i in empty_body[:5]:
    print("  EMPTY BODY:", i.get("artist"), "-", i.get("album"), i.get("url"))
for i in non_music:
    print("  NON_MUSIC:", i.get("artist"), "-", i.get("album"))

ok = (not missing_fields) and (not bad_type) and (not non_music)
print("VERIFY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
