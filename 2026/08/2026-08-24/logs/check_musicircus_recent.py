import json, glob, os

base = "/home/liyifan/music-record"
files = sorted(glob.glob(f"{base}/2026/**/musicircus_reviews.json", recursive=True))
for f in reversed(files):
    with open(f) as fh:
        d = json.load(fh)
    if d["meta"]["total"] != 0:
        print("MOST RECENT NON-EMPTY:", f, "total=", d["meta"]["total"])
        print("FIRST ITEM KEYS:", list(d["items"][0].keys()) if d["items"] else "none")
        print(json.dumps(d["items"][0], ensure_ascii=False, indent=2)[:3000] if d["items"] else "")
        break
