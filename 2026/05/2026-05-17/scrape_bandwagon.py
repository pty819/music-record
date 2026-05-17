import feedparser, json, re, html
from datetime import datetime, timezone, timedelta

feed = feedparser.parse('https://www.bandwagon.asia/feeds/articles.atom')
cutoff = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=3)
site_id = "bandwagon_asia"

# Keywords that indicate non-music content
NON_MUSIC = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD', 'Cannes', 'Film', 'Anime', 'Crunchyroll']

def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

items = []
for e in feed.entries:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if not pub:
        continue
    dt = datetime(*pub[:6], tzinfo=timezone(timedelta(hours=8)))
    if dt < cutoff:
        continue

    title = e.get('title', '')
    url = e.get('link', '')

    # Non-music filter
    skip = False
    for kw in NON_MUSIC:
        if kw.lower() in title.lower():
            skip = True
            break
    if skip:
        continue

    # Get full content from content[0].value (longer than summary)
    raw_content = e.get('content', [{}])
    if raw_content and isinstance(raw_content, list):
        raw = raw_content[0].get('value', '') if raw_content[0] else ''
    else:
        raw = raw_content.get('value', '') if hasattr(raw_content, 'get') else ''
    if not raw:
        raw = e.get('summary', '')

    excerpt = strip_html(raw)
    if len(excerpt) > 500:
        excerpt = excerpt[:500]

    item = {
        "album": None,
        "artist": None,
        "score": None,
        "url": url,
        "source": site_id,
        "pub_date": dt.strftime('%Y-%m-%d'),
        "tags": [],
        "excerpt": excerpt,
        "site_id": site_id,
        "crawl_status": "success",
        "type": "feature"
    }
    items.append(item)
    print(f"OK {dt.strftime('%m-%d')} | {title[:70]}")

print(f"\nTotal items: {len(items)}")
out = '/home/liyifan/music-record/2026/05/2026-05-17/bandwagon_asia_reviews.json'
with open(out, 'w') as f:
    json.dump(items, f, indent=2, ensure_ascii=False)
print(f"Written to {out}")