import json, sys
from collections import Counter

path = sys.argv[1]
d = json.load(open(path))
print('meta:', d['meta'])
items = d['items']
print('total items:', len(items))
print('crawl_status:', dict(Counter(i.get('crawl_status') for i in items)))
print('empty bodies:', sum(1 for i in items if not (i.get('body') or '').strip()))
print('partial:', sum(1 for i in items if i.get('crawl_status') == 'partial'))
dates = sorted(i['pub_date'] for i in items)
print('date range:', dates[0], '->', dates[-1])
