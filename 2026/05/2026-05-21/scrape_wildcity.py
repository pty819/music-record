import re, json, time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

SITE = "wild_city"
SITE_URL = "https://www.thewildcity.com"
DAYS_WINDOW = 3
CUTOFF = datetime.now() - timedelta(days=DAYS_WINDOW)
OUT_FILE = "/home/liyifan/music-record/2026/05/2026-05-21/wild_city_reviews.json"

NON_MUSIC = ["BLU-RAY", "BLU RAY", "UHD", "VOD", "DVD"]

results = []

def is_music(album, artist):
    text = f"{album} {artist}".upper()
    return not any(k in text for k in NON_MUSIC)

def parse_date(date_str):
    """Try to parse various date formats"""
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            pass
    return None

with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    context = browser.new_context(
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
    )
    page = context.new_page()

    print(f"Navigating to {SITE_URL}/")
    resp = page.goto(SITE_URL + "/", timeout=25)
    print(f"Status: {resp.status}")

    # Cookie banner
    try:
        banner = page.locator('text=/cookie/i').first
        if banner.is_visible(timeout=3000):
            btn = page.locator('text=/agree|accept|I agree/i').first
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_timeout(1000)
                print("Cookie banner dismissed")
    except Exception as e:
        print(f"No cookie banner: {e}")

    # Get all review links from homepage
    links = page.query_selector_all('a[href]')
    review_candidates = []
    for l in links:
        href = l.get_attribute('href') or ""
        text = (l.inner_text() or "").strip()
        if any(x in href.lower() for x in ['review', 'article', 'feature', 'interview', 'podcast']):
            if href.startswith('/'):
                href = SITE_URL + href
            if href not in [r[0] for r in review_candidates]:
                review_candidates.append((href, text[:100]))

    print(f"Found {len(review_candidates)} review/article links on homepage")
    for href, text in review_candidates[:10]:
        print(f"  {href} -> {text}")

    # Also look for a reviews listing page
    review_urls = [
        SITE_URL + "/reviews/",
        SITE_URL + "/category/reviews/",
        SITE_URL + "/reviews-2/",
        SITE_URL + "/music-reviews/",
    ]

    all_review_links = list(review_candidates)

    for rurl in review_urls:
        try:
            page.goto(rurl, timeout=15)
            print(f"Reviews page: {rurl} -> status OK")
            links2 = page.query_selector_all('a[href]')
            for l in links2:
                href = l.get_attribute('href') or ""
                text = (l.inner_text() or "").strip()
                if any(x in href.lower() for x in ['review', 'article', 'feature', 'interview', 'podcast']):
                    if href.startswith('/'):
                        href = SITE_URL + href
                    if href not in [r[0] for r in all_review_links]:
                        all_review_links.append((href, text[:100]))
            print(f"  Total links so far: {len(all_review_links)}")
        except Exception as e:
            print(f"Reviews page {rurl}: {e}")

    browser.close()

# Deduplicate
seen_urls = set()
deduped = []
for href, text in all_review_links:
    if href not in seen_urls:
        seen_urls.add(href)
        deduped.append((href, text))

print(f"\nTotal unique review links: {len(deduped)}")

# Now visit each review link and extract data
with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    context = browser.new_context(
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
    )

    for url, link_text in deduped[:30]:
        try:
            page = context.new_page()
            resp = page.goto(url, timeout=15)
            print(f"\nVisiting: {url} -> {resp.status}")

            # Check date
            date_text = ""
            try:
                # Look for date in common locations
                for sel in ['time', '.date', '.post-date', '.entry-date', '[class*="date"]', '.posted']:
                    el = page.query_selector(sel)
                    if el:
                        date_text = el.inner_text()
                        break
                if not date_text:
                    # Fall back to meta tags
                    date_text = page.query_selector('meta[property="article:published_time"]').get_attribute('content') or ""
            except:
                pass

            pub_date = None
            if date_text:
                pub_date = parse_date(date_text[:50])
                print(f"  Date text: {date_text[:50]} -> parsed: {pub_date}")

            if pub_date and pub_date < CUTOFF:
                print(f"  Skipping - older than {DAYS_WINDOW} days")
                page.close()
                continue

            # Get title
            title_el = page.query_selector('h1') or page.query_selector('h2') or page.query_selector('title')
            title = title_el.inner_text().strip() if title_el else link_text

            # Get artist/album info
            # Many review pages have "Artist - Album" format
            album = ""
            artist = ""
            parts = title.split(' - ', 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                album = parts[1].strip()
            else:
                album = title

            # Check for non-music
            if not is_music(album, artist):
                print(f"  Skipping non-music: {artist} - {album}")
                page.close()
                continue

            # Get score
            score = None
            try:
                score_el = page.locator('text=/\\d+\\/10|\\d+\\.\\d+\\/10|\\d+%/').first
                if score_el:
                    score_text = score_el.inner_text()
                    m = re.search(r'(\d+\.?\d*)\s*/\s*10', score_text)
                    if m:
                        score = float(m.group(1))
                    m = re.search(r'(\d+\.?\d*)\s*%', score_text)
                    if m:
                        score = float(m.group(1)) / 10  # Convert to /10
                    print(f"  Score: {score}")
            except:
                pass

            # Get excerpt/content
            excerpt = ""
            try:
                content_el = page.query_selector('.entry-content') or page.query_selector('.post-content') or page.query_selector('article') or page.query_selector('[class*="content"]')
                if content_el:
                    text = content_el.inner_text()
                    text = re.sub(r'<[^>]+>', '', text)
                    excerpt = text[:500].strip()
            except:
                pass

            # Determine type
            is_feature = any(x in url.lower() for x in ['feature', 'interview', 'podcast', 'topic'])
            rtype = "feature" if is_feature else "review"

            print(f"  Title: {title}")
            print(f"  Artist: {artist}, Album: {album}, Score: {score}")
            print(f"  Excerpt: {excerpt[:100]}...")

            results.append({
                "album": album,
                "artist": artist,
                "score": score,
                "url": url,
                "source": SITE,
                "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
                "tags": ["south asian", "alternative", "electronic"],
                "excerpt": excerpt[:500],
                "site_id": SITE,
                "crawl_status": "success",
                "type": rtype
            })

            page.close()
        except Exception as e:
            print(f"  Error: {e}")
            try:
                page.close()
            except:
                pass

    browser.close()

print(f"\n=== Total results: {len(results)} ===")
for r in results:
    print(f"  {r['artist']} - {r['album']} ({r['pub_date']}) - {r['score']}")

with open(OUT_FILE, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\nWritten to {OUT_FILE}")
