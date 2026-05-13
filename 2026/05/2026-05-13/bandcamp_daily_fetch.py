import sys, feedparser, json
from datetime import datetime, timedelta

content = sys.stdin.read()
print(f'Feed size: {len(content)} bytes', file=sys.stderr)

feed = feedparser.parse(content)
print(f'Entries: {len(feed.entries)}', file=sys.stderr)

now = datetime.utcnow()
cutoff = now - timedelta(days=7)
print(f'Cutoff: {cutoff.isoformat()}', file=sys.stderr)

recent = []
for e in feed.entries:
    if hasattr(e, 'published_parsed') and e.published_parsed:
        dt = datetime(*e.published_parsed[:6])
    elif hasattr(e, 'updated_parsed') and e.updated_parsed:
        dt = datetime(*e.updated_parsed[:6])
    else:
        dt = now

    age = (now - dt).days
    print(f'  [{age}d ago] {e.get("title", "no title")[:60]}', file=sys.stderr)

    if dt >= cutoff:
        recent.append({
            'title': e.get('title', ''),
            'url': e.get('link', ''),
            'published': dt.isoformat(),
            'summary': e.get('summary', '')[:500],
            'author': getattr(e, 'author', ''),
        })

print(f'Recent (7d): {len(recent)}', file=sys.stderr)
print(json.dumps(recent, indent=2))
