import feedparser, json, re
from datetime import datetime, timedelta

today = datetime(2026, 5, 12)
cutoff = today - timedelta(days=7)
print(f'Today: {today.date()}, Cutoff: {cutoff.date()}')

feed = feedparser.parse('https://rhythmpassport.com/feed/')
print(f'Total items: {len(feed.entries)}')
print(f'Last build date: {feed.feed.get("last_built_date", "N/A")}')

recent = []
for entry in feed.entries:
    try:
        pub = entry.get('published_parsed') or entry.get('updated_parsed')
        if pub:
            pub_date = datetime(*pub[:6])
        else:
            pub_date = None
    except:
        pub_date = None

    if pub_date:
        age = (today - pub_date).days
        in_range = cutoff <= pub_date <= today
    else:
        age = None
        in_range = False

    cats = [t.term for t in entry.get('tags', [])]
    recent.append({
        'title': entry.get('title', ''),
        'link': entry.get('link', ''),
        'pub_date': pub_date.strftime('%Y-%m-%d') if pub_date else None,
        'age_days': age,
        'in_range': in_range,
        'categories': cats
    })
    print(f"  {pub_date.strftime('%Y-%m-%d') if pub_date else 'N/A'} | {age}d ago | {'YES' if in_range else 'no'} | {entry.get('title', '')[:80]}")

print(f'\nIn last 7 days: {sum(1 for r in recent if r["in_range"])}')
