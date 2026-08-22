import json, re, sys
from collections import Counter

path = "/home/liyifan/music-record/2026/08/2026-08-23/boomkat_reviews.json"
d = json.load(open(path))
items = d["items"]
print("meta:", json.dumps(d["meta"], ensure_ascii=False))
print("count:", len(items))

missing_body = [i for i in items if not (i.get("body") or "").strip()]
missing_excerpt = [i for i in items if not (i.get("excerpt") or "").strip()]
bad_status = [i for i in items if i.get("crawl_status") != "success"]
print("missing body:", len(missing_body))
print("missing excerpt:", len(missing_excerpt))
print("non-success status:", len(bad_status), [b.get("crawl_status") for b in bad_status])

keys = set()
for i in items:
    keys.update(i.keys())
print("keys:", sorted(keys))

nonmusic = re.compile(r"\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)", re.I)
bad = [i for i in items if nonmusic.search(f"{i.get('artist','')} {i.get('album','')} {i.get('tags','')}")]
print("non-music leaked:", len(bad), [(i.get('artist'), i.get('album')) for i in bad])

cutoff = "2026-08-21"
too_old = [i for i in items if (i.get("pub_date") or "") < cutoff]
print("pre-cutoff items:", len(too_old))
print("pub_date distribution:", dict(Counter(i["pub_date"] for i in items)))
print("types:", dict(Counter(i.get("type") for i in items)))
