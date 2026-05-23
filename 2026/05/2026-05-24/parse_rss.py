import feedparser, re
from datetime import datetime, timezone

cutoff = datetime.now(timezone.utc).timestamp() - 3 * 86400
print('Cutoff timestamp:', cutoff)

feed = feedparser.parse('sea_of_tranquility_rss.xml')
print('Total entries:', len(feed.entries))
for i, e in enumerate(feed.entries[:5]):
    print(f'--- entry {i} ---')
    print('title:', e.get('title',''))
    print('published:', e.get('published',''))
    print('link:', e.get('link',''))
    # check summary
    summary = e.get('summary','') or e.get('description','') or ''
    print('summary len:', len(summary))
    # strip HTML
    clean = re.sub(r'<[^>]+>', '', summary)
    print('summary (clean, first 200):', clean[:200])
    # check for enclosures/media
    print('media content?', bool(e.get('media_content')))
    print('links:', e.get('links',''))