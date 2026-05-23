import json
with open('bandcamp_daily_reviews.json') as f:
    data = json.load(f)
for item in data:
    print(json.dumps(item, indent=2, ensure_ascii=False))
    print('---')