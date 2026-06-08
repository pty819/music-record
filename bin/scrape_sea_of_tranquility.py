#!/usr/bin/env python3
"""
scrape_sea_of_tranquility.py — Sea of Tranquility reviewer scraper.

Direct urllib HTTP (no Camoufox), 36h cutoff, early-stop on consecutive
out-of-window reviews, CLI args for limit/days/date.

Output schema (canonical, must match RSS + other HTML scripts):
{
  "meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."},
  "items": [
    {album, artist, score, url, source, pub_date, tags, excerpt, body,
     site_id, crawl_status, type}
  ]
}

Usage:
  python3 scrape_sea_of_tranquility.py --days 1.5 --limit 30
  python3 scrape_sea_of_tranquility.py --date 2026-06-08
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = 'https://www.seaoftranquility.org'
DEFAULT_OUTPUT = '/home/liyifan/music-record/2026/06/2026-06-08'
OUTFILE_NAME = 'sea_of_tranquility_reviews.json'
SOURCE = 'Sea of Tranquility'
SITE_ID = 'sea_of_tranquility'
HTTP_TIMEOUT = 15          # single-fetch timeout (was 20 in v2, tightened)
SLEEP_BETWEEN = 0.25       # polite delay between review fetches
EARLY_STOP_AFTER = 5       # consecutive out-of-window reviews → break

months_map = {
    'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
    'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12,
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 10, 'Dec': 12,
}


def parse_args():
    p = argparse.ArgumentParser(
        description="Sea of Tranquility scraper (urllib + 36h cutoff + early-stop)")
    p.add_argument("--days", type=float, default=1.5,
                   help="Max age in days (default 1.5 = 36h)")
    p.add_argument("--date", type=str, default=None,
                   help="Explicit cutoff date YYYY-MM-DD (overrides --days)")
    p.add_argument("--limit", type=int, default=30,
                   help="Max reviews to fetch from listing (default 30, was 100 in v2)")
    p.add_argument("--out-dir", type=str,
                   default=os.environ.get('HERMES_KANBAN_WORKSPACE', DEFAULT_OUTPUT),
                   help="Output directory (defaults to $HERMES_KANBAN_WORKSPACE)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print counts, do not write file")
    return p.parse_args()


def parse_added_date(text):
    """Parse 'Added: June 1st 2026' from text."""
    m = re.search(r'Added:\s*([A-Za-z]+)\s+(\d+)(?:st|nd|rd|th)?,?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = months_map.get(m.group(1))
        day = int(m.group(2))
        year = int(m.group(3))
        if month and 1 <= day <= 31 and year > 2000:
            return datetime(year, month, day, tzinfo=timezone.utc)
    return None


def parse_score(text):
    """Extract score value (1-10)."""
    for pat in (r'(?:Score|Rating)[:\s]*(\d+(?:\.\d+)?)\s*/?\s*(?:\d+)?',
                r'(?:Score|Rating)[:\s]*(\d+(?:\.\d+)?)'):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 1 <= val <= 10:
                return val
    return None


def strip_html(text):
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&#39;', "'", text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_body_best(html):
    """Extract review body from HTML; <p> tags first, <td> fallback."""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    ps = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
    body_parts = []
    for p in ps:
        text = strip_html(p)
        if len(text) < 20:
            continue
        if any(kw in text.lower() for kw in ['click here', 'copyright', 'all logos',
                                              'contact us', 'web destination',
                                              'main menu', 'faq page',
                                              'visit our friends', 'printer friendly']):
            continue
        body_parts.append(text)
    if body_parts:
        return '\n\n'.join(body_parts)
    tds = re.findall(r'<td[^>]*>(.*?)</td>', html, re.DOTALL)
    candidates = []
    for td in tds:
        text = strip_html(td)
        if len(text) < 200:
            continue
        text_lower = text.lower()
        if text_lower.startswith(('&middot;', '·', 'for information', 'all logos',
                                   'click here', 'copyright', 'visit our', 'search',
                                   'topics', 'sections', 'main menu')):
            continue
        text = re.sub(r'\s*\[?\s*Printer Friendly Page\s*\]?\s*\[?\s*Send to a Friend\s*\]?\s*$', '', text, flags=re.IGNORECASE)
        candidates.append((len(text), text))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return ''


def fetch(url, label=''):
    """Single HTTP GET with HTTP_TIMEOUT. Returns latin-1 decoded HTML."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    })
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read().decode('latin-1', errors='replace')


def build_item(rid, title, page, is_new):
    body = extract_body_best(page)
    added_date = parse_added_date(page)
    score = parse_score(page)
    url = f'{BASE}/reviews.php?op=showcontent&id={rid}'
    artist, album, rtype = '', title, 'review'
    if ':' in title:
        artist = title[:title.index(':')].strip()
        album = title[title.index(':') + 1:].strip()
    if not artist:
        rtype = 'feature'
    return {
        'album': album,
        'artist': artist,
        'score': score,
        'url': url,
        'source': SOURCE,
        'pub_date': added_date.isoformat() if added_date else None,
        'tags': ['new_this_week'] if is_new else [],
        'excerpt': body[:500] if body else '',
        'body': body,
        'site_id': f'sot_review_{rid}',
        'crawl_status': 'ok',
        'type': rtype,
    }


def main():
    args = parse_args()
    now = datetime.now(timezone.utc)
    if args.date:
        cutoff_dt = datetime.strptime(args.date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    else:
        cutoff_dt = now - timedelta(days=args.days)

    out_dir = args.out_dir
    out_path = os.path.join(out_dir, OUTFILE_NAME)

    print(f"SoT scraper — now={now.isoformat()} cutoff={cutoff_dt.isoformat()} "
          f"limit={args.limit} days={args.days}", file=sys.stderr)

    # 1. Fetch listing
    print('1) Fetching listing...', file=sys.stderr)
    listing_html = fetch(f'{BASE}/reviews.php', 'listing')

    # 2. Parse all review IDs and titles from listing
    all_ids = []
    for m in re.finditer(r'showcontent(?:&amp;|&)id=(\d+)', listing_html):
        rid = int(m.group(1))
        if rid not in all_ids:
            all_ids.append(rid)
    print(f'   Found {len(all_ids)} unique IDs', file=sys.stderr)

    new_ids = []
    for m in re.finditer(r'showcontent(?:&amp;|&)id=(\d+)[^>]*>[^<]*?(?:<[^>]+>)*?(?:&nbsp;)*?<img src="[^"]*newblue', listing_html):
        new_ids.append(int(m.group(1)))

    raw_titles = {}
    for m in re.finditer(r'showcontent(?:&amp;|&)id=(\d+)"[^>]*>(.*?)</a>', listing_html, re.DOTALL):
        rid = int(m.group(1))
        title = re.sub(r'<[^>]+>', '', m.group(2)).replace('&nbsp;', ' ').strip()
        if rid not in raw_titles:
            raw_titles[rid] = title

    skip_pat = re.compile(r'\b(BLU-RAY|UHD|VOD|DVD|Blu-ray|4K)\b', re.IGNORECASE)
    to_fetch = [(rid, raw_titles[rid]) for rid in all_ids
                if rid in raw_titles and not skip_pat.search(raw_titles[rid])]
    to_fetch = to_fetch[:args.limit]
    print(f'   After non-music filter + limit: {len(to_fetch)} to fetch', file=sys.stderr)

    # 3. Fetch each review, with early-stop
    print(f'\n2) Fetching reviews (early-stop after {EARLY_STOP_AFTER} consecutive out-of-window)...',
          file=sys.stderr)
    results = []
    in_window = 0
    consecutive_miss = 0

    for idx, (rid, title) in enumerate(to_fetch):
        try:
            page = fetch(f'{BASE}/reviews.php?op=showcontent&id={rid}', f'id={rid}')
        except Exception as e:
            print(f'   [{idx+1}/{len(to_fetch)}] id={rid} FETCH ERROR: {e}', file=sys.stderr)
            consecutive_miss += 1
            if consecutive_miss >= EARLY_STOP_AFTER:
                print(f'   Early-stop: {EARLY_STOP_AFTER} consecutive fetch failures',
                      file=sys.stderr)
                break
            continue

        item = build_item(rid, title, page, is_new=(rid in new_ids))
        added_date = parse_added_date(page)

        if added_date and added_date < cutoff_dt:
            # out of window: skip, but don't count toward early-stop (date-based)
            # early-stop only triggers on actual out-of-window reviews with date
            consecutive_miss += 1
            if consecutive_miss >= EARLY_STOP_AFTER:
                print(f'   Early-stop at idx={idx+1}: {EARLY_STOP_AFTER} consecutive '
                      f'out-of-window reviews (latest pub_date={added_date.isoformat()})',
                      file=sys.stderr)
                break
            continue

        # In window (or no date available → include as feature)
        consecutive_miss = 0
        results.append(item)
        if added_date and added_date >= cutoff_dt:
            in_window += 1

        if (idx + 1) % 10 == 0:
            print(f'   Progress: {idx+1}/{len(to_fetch)}, kept={len(results)}', file=sys.stderr)
        time.sleep(SLEEP_BETWEEN)

    print(f'\n3) Results: {len(results)} items, in_window={in_window}', file=sys.stderr)

    output = {
        'meta': {
            'total': len(results),
            'scraped_at': now.isoformat(),
            'cutoff_date': cutoff_dt.isoformat(),
        },
        'items': results,
    }

    if args.dry_run:
        print(json.dumps(output['meta'], indent=2))
        return

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'   Wrote {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
