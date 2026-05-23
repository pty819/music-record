from playwright.sync_api import sync_playwright
from datetime import datetime, timezone, timedelta
import re
import json
import html as html_mod

SITE = "theclassicreview"
OUTPUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-24/the_classic_review_reviews.json"
CUTOFF_DAYS = 3
MAX_PAGES = 2

def strip_html(text):
    text = html_mod.unescape(text or "")
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]

def parse_date(date_str, page=None):
    """Parse TCR date formats."""
    date_str = strip_html(date_str).strip()
    for fmt in ['%B %d, %Y', '%b %d, %Y', '%d %B %Y']:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except:
            pass
    return None

results = []
seen_urls = set()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()

    # Accept cookies
    page.goto("https://theclassicreview.com/", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    try:
        page.locator("text=Accept").first.click(timeout=3000)
        page.wait_for_timeout(1000)
    except:
        pass

    NOW = datetime.now(timezone.utc)
    CUTOFF = NOW - timedelta(days=CUTOFF_DAYS)
    print(f"Cutoff: {CUTOFF.date()} (3-day window)")

    # Scrape listing pages
    for page_num in range(1, MAX_PAGES + 1):
        listing_url = f"https://theclassicreview.com/category/album-reviews/page/{page_num}/" if page_num > 1 else "https://theclassicreview.com/category/album-reviews/"
        print(f"\n=== Listing page {page_num}: {listing_url} ===")

        resp = page.goto(listing_url, timeout=30000, wait_until="networkidle")
        print(f"Status: {resp.status}")

        # Get all article links from this page (dedupe by href)
        all_links = page.locator('a[href*="/album-reviews/"]').all()
        article_map = {}
        for l in all_links:
            href = l.get_attribute('href') or ''
            if 'page/' in href or 'category/' in href or href in seen_urls:
                continue
            # Get date from this link's text if it looks like a date
            txt = l.inner_text().strip()
            if re.match(r'\w+ \d{1,2}, \d{4}', txt):
                article_map[href] = (strip_html(txt), txt)
            elif href not in article_map:
                article_map[href] = (txt, None)

        print(f"Unique article URLs: {len(article_map)}")
        for href, (title, date_text) in list(article_map.items())[:10]:
            print(f"  [{date_text or '?'}] {title[:60]}")

        # Process each article
        for href, (title, date_text) in article_map.items():
            if href in seen_urls:
                continue
            seen_urls.add(href)

            print(f"\n  Visiting: {href}")
            try:
                page.goto(href, timeout=20000, wait_until="networkidle")
                page.wait_for_timeout(1000)
            except Exception as e:
                print(f"    Navigation error: {e}")
                continue

            page_url = page.url

            # Get article date
            article_date = None
            # Try time element
            try:
                dt_attr = page.locator('time[datetime]').first.get_attribute("datetime")
                if dt_attr:
                    article_date = datetime.fromisoformat(dt_attr.replace('Z', '+00:00')).astimezone(timezone.utc)
            except:
                pass

            # Try meta display date
            if not article_date:
                try:
                    meta_dates = page.locator('.post-meta, .entry-meta, [class*="date"], [class*="time"]').all_text_contents()
                    for md in meta_dates[:5]:
                        parsed = parse_date(md)
                        if parsed:
                            article_date = parsed
                            break
                except:
                    pass

            if not article_date and date_text:
                article_date = parse_date(date_text)

            if not article_date:
                # Fallback: scan page for date pattern
                body = page.locator('body').inner_text()
                m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', body)
                if m:
                    article_date = parse_date(m.group(0))

            if article_date:
                age_days = (NOW - article_date).days
                print(f"    Date: {article_date.date()} ({age_days}d old)")
                if article_date < CUTOFF:
                    print(f"    OLD (>{CUTOFF_DAYS}d), skipping")
                    continue

            # Type detection
            is_feature = bool(re.search(r'/best-of/|/classics-revisited/', page_url))
            item_type = "feature" if is_feature else "review"

            # Extract title
            h1 = strip_html(page.locator('h1, .entry-title').first.inner_text()) if page.locator('h1, .entry-title').count() else title

            # Artist/album from title
            review_match = re.match(r'Review:\s*(.+?)\s*[-–—]\s*(.+?)(?:\s*\((.*)\)\s*)?$', h1)
            if review_match:
                artist_raw = review_match.group(1).strip()
                album = review_match.group(2).strip()
            else:
                album = h1
                artist_raw = None

            # Score - TCR uses star ratings
            score = None
            try:
                # TCR has rating text like "9/10" or star elements
                rating_els = page.locator('[class*="rating"], .wp-star-rating, [class*="score"]').all()
                for el in rating_els:
                    txt = strip_html(el.inner_text())
                    m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+)', txt)
                    if m:
                        score = float(m.group(1)) / float(m.group(2)) * 100
                        break
            except:
                pass

            # Tags
            tags = []
            try:
                tag_els = page.locator('.cat-links a, [rel="tag"], .post-tags a').all()
                for t in tag_els:
                    tag_text = strip_html(t.inner_text())
                    if tag_text:
                        tags.append(tag_text)
            except:
                pass
            tags = tags[:10]

            # Excerpt from body
            try:
                content_el = page.locator('.entry-content, .post-content, article .content').first
                full_text = strip_html(content_el.inner_text())
                excerpt_text = full_text[:500]
            except:
                excerpt_text = ""

            # Paywall check
            page_text = page.locator('body').inner_text().lower()
            is_paywalled = any(kw in page_text for kw in ['subscribe to read', 'premium only', 'members only'])
            if is_paywalled:
                print(f"    [PAYWALLED] skipping")
                continue

            result = {
                "album": album[:200],
                "artist": artist_raw[:200] if artist_raw else None,
                "score": round(score, 1) if score is not None else None,
                "url": page_url,
                "source": "The Classic Review",
                "pub_date": article_date.isoformat() if article_date else None,
                "tags": tags,
                "excerpt": excerpt_text[:500],
                "site_id": SITE,
                "crawl_status": "success",
                "type": item_type
            }
            results.append(result)
            print(f"    [{item_type}] album={album[:50]} score={score} date={article_date.date() if article_date else '?'}")

    browser.close()

# Save
print(f"\n=== Total results: {len(results)} ===")
for r in results:
    print(f"  [{r['type']}] {r['album'][:50]} | score={r['score']} | {r.get('pub_date', '?')[:10]}")

with open(OUTPUT_FILE, 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nSaved {len(results)} items to {OUTPUT_FILE}")
if results:
    print(f"Type breakdown: review={sum(1 for r in results if r['type']=='review')}, feature={sum(1 for r in results if r['type']=='feature')}")