import feedparser, json, re, html
from datetime import datetime, timezone, timedelta

feed = feedparser.parse('https://www.bandwagon.asia/feeds/articles.atom')
cutoff = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=3)
site_id = "bandwagon_asia"

NON_MUSIC_KEYWORDS = ['BLU-RAY', 'BLU RAY', 'UHD', 'VOD', 'DVD', 'Cannes', 'Film', 'Anime', 'Crunchyroll']

def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_summary(entry):
    raw = entry.get('summary_detail', entry).get('value', '') or entry.get('summary', '')
    return strip_html(raw)

# First, let's inspect what categories/tags are available
for e in feed.entries[:15]:
    pub = e.get('published_parsed') or e.get('updated_parsed')
    if pub:
        dt = datetime(*pub[:6], tzinfo=timezone(timedelta(hours=8)))
    else:
        dt = None
    in_window = dt >= cutoff if dt else False
    tags = [t['term'] for t in e.get('tags', [])]
    print(f"[{'IN' if in_window else 'OUT'}] tags={tags} | {e.get('title','')[:60]}")