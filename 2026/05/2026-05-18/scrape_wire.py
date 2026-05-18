import sys, re

content = sys.stdin.read()
print('Length:', len(content))

articles = re.findall(r'<article[^>]*>(.*?)</article>', content, re.DOTALL)
print('Articles found:', len(articles))

for i, a in enumerate(articles[:10]):
    h = re.findall(r'<h[1-4][^>]*>(.*?)</h[1-4]>', a, re.DOTALL)
    print(f'--- Article {i} ---')
    for hh in h[:3]:
        clean = re.sub(r'<[^>]+>', '', hh).strip()
        print(clean[:120])