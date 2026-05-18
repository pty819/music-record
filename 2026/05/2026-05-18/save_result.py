import json

reviews = []

with open('/home/liyifan/music-record/2026/05/2026-05-18/roots_world_reviews.json', 'w') as f:
    json.dump(reviews, f, indent=2)

print("Done. Output: [] (0 items)")