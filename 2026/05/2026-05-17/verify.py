import json
d = json.load(open('/home/liyifan/music-record/2026/05/2026-05-17/bandwagon_asia_reviews.json'))
print(f'Items: {len(d)}')
for x in d:
    print(f"  {x['pub_date']} | {x['type']} | score={x['score']} | {x['url'][-60:]}")