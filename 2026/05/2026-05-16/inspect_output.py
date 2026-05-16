import json
with open('/home/liyifan/music-record/2026/05/2026-05-16/avant_music_news_reviews.json') as f:
    data = json.load(f)
print(f'Total: {len(data)}')
for item in data:
    print(f'  [{item["type"]:7}] {item.get("artist","") or "??"} - {item.get("album","")} | date={item["pub_date"][:10]}')
