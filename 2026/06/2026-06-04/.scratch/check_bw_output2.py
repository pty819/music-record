#!/usr/bin/env python3
import json
with open('/home/liyifan/music-record/2026/06/2026-06-04/bandwagon_asia_reviews.json') as f:
    d = json.load(f)
for i in d['items']:
    print(f"URL: {i['url'][:80]}")
    print(f"  artist: '{i['artist']}'")
    print(f"  album: '{i['album'][:80]}'")
    print(f"  type: {i['type']}")
    print(f"  excerpt: '{i['excerpt'][:100]}'")
    print()
