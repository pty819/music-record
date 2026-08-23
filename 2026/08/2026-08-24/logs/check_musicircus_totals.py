import json, glob, os

base = "/home/liyifan/music-record"
files = sorted(glob.glob(f"{base}/2026/08/2026-08-*/musicircus_reviews.json"))
for f in files[-6:]:
    with open(f) as fh:
        d = json.load(fh)
    print(os.path.basename(os.path.dirname(f)), "total=", d["meta"]["total"], "items=", len(d["items"]))

print("--- all aug non-empty ---")
for f in sorted(glob.glob(f"{base}/2026/08/*/musicircus_reviews.json")):
    with open(f) as fh:
        d = json.load(fh)
    if d["meta"]["total"] != 0:
        print(f, "total=", d["meta"]["total"])
