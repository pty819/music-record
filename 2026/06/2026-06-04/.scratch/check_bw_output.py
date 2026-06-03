#!/usr/bin/env python3
import json
with open('/home/liyifan/music-record/2026/06/2026-06-04/bandwagon_asia_reviews.json') as f:
    d = json.load(f)
print(f'Total: {d["meta"]["total"]}')
print(f'Scraped: {d["meta"]["scraped_at"]}')
print(f'Cutoff: {d["meta"]["cutoff_date"]}')
for i in d['items']:
    print(f'  [{i["type"]}] artist="{i["artist"]}" album="{i["album"][:50]}" date={i["pub_date"]} body_len={len(i["body"])}')
