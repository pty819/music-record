import sys, re
from datetime import datetime, timedelta

content = sys.stdin.read()
items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
print(f'Total items: {len(items)}')
cutoff = datetime.now() - timedelta(days=3)
now = datetime.now()

for item in items:
    title_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item) or re.search(r'<title>(.*?)</title>', item)
    date_match = re.search(r'<pubDate>(.*?)</pubDate>', item)
    link_match = re.search(r'<link>(.*?)</link>', item)
    desc_match = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item) or re.search(r'<description>(.*?)</description>', item)

    title = title_match.group(1).strip() if title_match else '?'
    link = link_match.group(1).strip() if link_match else '?'
    date_str = date_match.group(1).strip() if date_match else None

    if date_str:
        try:
            d = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S +0000')
            age_days = (now - d).days
            in_window = age_days <= 3
            flag = '✓' if in_window else '✗'
            # Clean HTML from description
            desc = ''
            if desc_match:
                desc = re.sub(r'<[^>]+>', '', desc_match.group(1))
                desc = desc.strip()[:100]
            print(f'{flag} [{age_days}d] {title[:70]} | {link}')
            if desc:
                print(f'   DESC: {desc[:80]}')
        except Exception as e:
            print(f'  [date parse error: {e}] {title[:60]}')
    else:
        print(f'  [no date] {title[:60]}')