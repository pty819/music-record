import json, re, sys

d = json.load(open('boomkat_pass1.json'))
items = d['items']
req = ['album', 'artist', 'score', 'url', 'source', 'pub_date', 'tags', 'excerpt', 'body', 'site_id', 'crawl_status', 'type']
missing = {}
for i in items:
    for k in req:
        if k not in i:
            missing.setdefault(k, []).append(i.get('album', '?'))
print('meta:', d['meta'])
print('total items:', len(items))
print('missing required fields:', {k: len(v) for k, v in missing.items()} if missing else 'NONE')
print('empty body:', sum(1 for i in items if not (i.get('body') or '').strip()))
print('empty excerpt:', sum(1 for i in items if not (i.get('excerpt') or '').strip()))
print('type values:', sorted(set(i.get('type') for i in items)))
print('site_id all boomkat:', all(i.get('site_id') == 'boomkat' for i in items))
nmd = [i for i in items if re.search(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', f"{i.get('artist','')} {i.get('album','')} {i.get('tags','')}", re.I)]
print('non-music items (should be 0):', len(nmd))
for i in nmd[:5]:
    print('   NON-MUSIC:', i.get('artist'), '-', i.get('album'))
print('body min/avg chars:', min(len(i['body']) for i in items), sum(len(i['body']) for i in items) // len(items))
# sanity: sample 2 items' full shape
print('\n--- SAMPLE ITEM 0 ---')
print(json.dumps(items[0], ensure_ascii=False, indent=2)[:800])
print('\n--- SAMPLE ITEM 50 ---')
print(json.dumps(items[50], ensure_ascii=False, indent=2)[:800])
