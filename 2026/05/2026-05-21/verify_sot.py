import json
with open('/home/liyifan/music-record/2026/05/2026-05-21/sea_of_tranquility_reviews.json') as f:
    items = json.load(f)
print(f'Total items: {len(items)}')
for item in items:
    print(f'  - {item["album"]} / {item["artist"]} / {item["pub_date"]} / score={item["score"]}')
    text = (item.get('album','') + ' ' + (item.get('artist') or '')).lower()
    blurs = any(kw in text for kw in ['blu-ray','(blu ray','(uhd','(vod','(dvd'])
    print(f'    Blu-ray filter: {"SKIP" if blurs else "KEEP"}')