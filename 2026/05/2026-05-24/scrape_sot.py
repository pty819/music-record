import html
import json, re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

CUTOFF_DAYS = 3
OUTPUT_FILE = "sea_of_tranquility_reviews.json"
BASE_URL = "https://www.seaoftranquility.org/reviews.php"
NON_MUSIC_PATTERNS = ["(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)"]

def clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_date(date_str):
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str.strip())
    try:
        dt = datetime.strptime(date_str, "%B %d %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except:
        return None

def get_type_from_title(title):
    t = title.lower()
    if any(p in t for p in ['interview', 'feature', 'preview', 'exclusive', 'spotlight']):
        return 'feature'
    if any(p in t for p in ['tracklist', 'track list', 'tracklisting']):
        return 'tracklist'
    return 'review'

print("Starting Sea of Tranquility scraper...")

results = []
seen_ids = set()
cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)).timestamp()
print("Cutoff: " + str(cutoff_ts) + " (3 days ago)")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    with browser.new_page() as page:
        print("Navigating to " + BASE_URL + "...")
        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)
        html_content = page.content()

        # newgreen = within 3 days, newblue = this week (may or may not be in window)
        green_pat = re.compile(r'<a href="(reviews\.php\?op=showcontent&amp;id=(\d+))">([^<]+)\s*<img src="images/newgreen\.gif"')
        blue_pat = re.compile(r'<a href="(reviews\.php\?op=showcontent&amp;id=(\d+))">([^<]+)\s*<img src="images/newblue\.gif"')

        green_items = list(green_pat.finditer(html_content))
        blue_items = list(blue_pat.finditer(html_content))

        print("newgreen (within 3 days): " + str(len(green_items)))
        print("newblue (this week): " + str(len(blue_items)))

        for m in green_items:
            title = html.unescape(re.sub(r'\s*<[^>]+>\s*', '', m.group(3)).strip())
            title = re.sub(r'\s+', ' ', title).strip()
            rid = m.group(2)
            if rid not in seen_ids:
                seen_ids.add(rid)
                results.append({
                    'album': title,
                    'artist': None,
                    'score': None,
                    'url': 'https://www.seaoftranquility.org/' + m.group(1).replace('&amp;', '&'),
                    'source': 'seaoftranquility.org',
                    'pub_date': None,
                    'tags': [],
                    'excerpt': '',
                    'site_id': 'seaoftranquility',
                    'crawl_status': 'pending',
                    'type': get_type_from_title(title)
                })
                print("  GREEN: " + title[:60])

        for m in blue_items:
            title = html.unescape(re.sub(r'\s*<[^>]+>\s*', '', m.group(3)).strip())
            title = re.sub(r'\s+', ' ', title).strip()
            rid = m.group(2)
            if rid not in seen_ids:
                seen_ids.add(rid)
                results.append({
                    'album': title,
                    'artist': None,
                    'score': None,
                    'url': 'https://www.seaoftranquility.org/' + m.group(1).replace('&amp;', '&'),
                    'source': 'seaoftranquility.org',
                    'pub_date': None,
                    'tags': [],
                    'excerpt': '',
                    'site_id': 'seaoftranquility',
                    'crawl_status': 'pending',
                    'type': get_type_from_title(title)
                })
                print("  BLUE: " + title[:60])

    browser.close()

print("\nTotal items to check: " + str(len(results)))

final_results = []
for item in results:
    if any(p in item['album'] for p in NON_MUSIC_PATTERNS):
        continue

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            with browser.new_page() as page:
                page.goto(item['url'], wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)
                html_content = page.content()

                m = re.search(r'<b>Added:</b>\s*([A-Z][a-z]+ \d+\w* \d{4})', html_content)
                if m:
                    item['pub_date'] = parse_date(m.group(1))

                whole = len(re.findall('star_whole', html_content))
                half = len(re.findall('star_half', html_content))
                if whole > 0:
                    item['score'] = float(whole) + (0.5 if half > 0 else 0)

                idx = html_content.find('<blockquote>')
                if idx >= 0:
                    review_html = html_content[idx:idx+2000]
                    end_idx = review_html.find('</blockquote>')
                    if end_idx >= 0:
                        review_html = review_html[:end_idx]
                    item['excerpt'] = clean_html(review_html)[:500]

                if item['pub_date']:
                    try:
                        dt = datetime.fromisoformat(item['pub_date'])
                        if dt.timestamp() < cutoff_ts:
                            item['crawl_status'] = 'old_cutoff'
                            print("  OLD (skip): " + item['album'][:60] + " | " + item['pub_date'])
                        else:
                            item['crawl_status'] = 'success'
                            print("  OK: [" + item['type'] + "] " + item['album'][:55] + " | score=" + str(item['score']) + " | " + item['pub_date'][:10])
                    except:
                        item['crawl_status'] = 'success'
                else:
                    item['crawl_status'] = 'success'

                if item['type'] == 'feature':
                    item['score'] = None

            browser.close()
    except Exception as e:
        print("  Error: " + str(e))
        item['crawl_status'] = 'error'

    if item.get('crawl_status') == 'success':
        final_results.append(item)

print("\nFinal items: " + str(len(final_results)))

with open(OUTPUT_FILE, 'w') as f:
    json.dump(final_results, f, indent=2)
print("Written: " + OUTPUT_FILE)

for r in final_results:
    print("  [" + r['type'] + "] score=" + str(r['score']) + " | " + r['album'][:70] + " | " + str(r['pub_date']))