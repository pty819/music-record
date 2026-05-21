import subprocess, re, json, os, sys

def fetch(url):
    result = subprocess.run(['curl', '-s', '--max-time', '10', url], capture_output=True)
    return result.stdout.decode('latin-1')

def parse_score(html):
    full = len(re.findall(r'star_whole\.gif', html))
    half = len(re.findall(r'star_half\.gif', html))
    return full + half * 0.5

def parse_review(id):
    url = f'https://www.seaoftranquility.org/reviews.php?op=showcontent&id={id}'
    html = fetch(url)
    if 'File not found' in html or not re.search(r'Review:', html):
        return None
    title_match = re.search(r'Review:\s*"([^"]+)"', html)
    if not title_match:
        return None
    title = title_match.group(1)
    date_match = re.search(r'<b>Added:</b>\s*([A-Za-z]+\s+\d+th?\s+\d+)', html)
    if not date_match:
        return None
    date_str = date_match.group(1)
    reviewer_match = re.search(r'Reviewer:\s*<a[^>]*>([^<]+)</a>', html)
    reviewer = reviewer_match.group(1) if reviewer_match else None
    score = parse_score(html)
    # Fixed: <p align=justify> ... <b>Added:
    body_match = re.search(r'<p align=justify>(.*?)<b>Added:', html, re.DOTALL)
    body = ''
    if body_match:
        raw = body_match.group(1)
        body = re.sub(r'<[^>]+>', ' ', raw)
        body = re.sub(r'\s+', ' ', body).strip()
    excerpt = body[:500].strip() if body else ''
    parts = title.split(':')
    if len(parts) >= 2:
        artist = parts[0].strip()
        album = parts[1].strip()
    else:
        artist = None
        album = title
    return {
        'album': album,
        'artist': artist,
        'score': score,
        'url': url,
        'source': 'Sea of Tranquility',
        'pub_date': date_str,
        'tags': ['prog', 'fusion', 'metal', 'jazz-rock'],
        'excerpt': excerpt,
        'site_id': 'sea_of_tranquility',
        'crawl_status': 'success',
        'type': 'review'
    }

os.chdir('/home/liyifan/music-record/2026/05/2026-05-21')
print(f'CWD: {os.getcwd()}')
results = []
for id in [25536, 25537, 25538]:
    r = parse_review(id)
    if r:
        results.append(r)
        print(f'ID {id}: {r["album"]} | {r["artist"]} | {r["pub_date"]} | Score: {r["score"]} | Excerpt len: {len(r["excerpt"])}')
    else:
        print(f'ID {id}: FAILED')

print(f'Total: {len(results)} reviews')
sys.stdout.flush()

out_path = '/home/liyifan/music-record/2026/05/2026-05-21/sea_of_tranquility_reviews.json'
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print(f'Written to {out_path}')
print(f'File size: {os.path.getsize(out_path)} bytes')

# Verify by reading back
with open(out_path, 'r') as f:
    content = f.read()
print(f'Read back {len(content)} bytes')
print(content[:200])