#!/usr/bin/env python3
"""
froots scraper using Playwright Chromium
"""
import subprocess, json, time, re
from datetime import datetime, timedelta
from pathlib import Path

WORKDIR = Path("/home/liyifan/music-record/2026/05/2026-05-24")
OUTPUT_FILE = WORKDIR / "froots_reviews.json"

CUTOFF_DAYS = 3
MAX_PAGES = 2
MUSIC_EXCLUDE_RE = re.compile(r'(BLU-RAY|UHD|VOD|DVD)', re.IGNORECASE)

now = datetime.now()
cutoff = now - timedelta(days=CUTOFF_DAYS)
print(f"[froots] Cutoff: {cutoff.date()} | Today: {now.date()}")

results = []

# ─── Step 1: Try RSS feed ────────────────────────────────────────────────────
print("\n[Step 1] Trying RSS feed...")
rss_url = "https://frootsmag.com/feed/"

try:
    result = subprocess.run(
        ["curl", "-s", "--max-time", "20", "-L", rss_url],
        capture_output=True, text=True, timeout=25
    )
    if result.returncode == 0 and result.stdout.strip():
        with open("/tmp/froots_feed.xml", "w") as f:
            f.write(result.stdout)
        print("  → RSS fetched, parsing with feedparser...")
        try:
            import feedparser
            feed = feedparser.parse("/tmp/froots_feed.xml")
            entries = feed.entries
            print(f"  → {len(entries)} entries in feed")
            
            for entry in entries:
                pub_date_str = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    t = entry.published_parsed
                    if isinstance(t, tuple):
                        pub_date = datetime(*t[:6])
                        pub_date_str = pub_date.strftime("%Y-%m-%d")
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    t = entry.updated_parsed
                    if isinstance(t, tuple):
                        pub_date = datetime(*t[:6])
                        pub_date_str = pub_date.strftime("%Y-%m-%d")
                
                if not pub_date_str:
                    continue
                
                pub_dt = datetime.strptime(pub_date_str, "%Y-%m-%d")
                if pub_dt < cutoff:
                    continue

                url = entry.get('link', '')
                title = entry.get('title', '')

                if MUSIC_EXCLUDE_RE.search(title):
                    print(f"  SKIP (non-music): {title[:60]}")
                    continue

                excerpt = ""
                if hasattr(entry, 'summary'):
                    summary = entry.summary or ""
                    excerpt = re.sub(r'<[^>]+>', '', summary).strip()[:500]

                title_lower = title.lower()
                if any(k in title_lower for k in ['interview', 'feature', 'spotlight', 'profile', 'in conversation']):
                    item_type = "feature"
                    score = None
                else:
                    item_type = "review"
                    score = None

                results.append({
                    "album": title,
                    "artist": "",
                    "score": score,
                    "url": url,
                    "source": "frootsmag.com",
                    "pub_date": pub_date_str,
                    "tags": [],
                    "excerpt": excerpt,
                    "site_id": "froots",
                    "crawl_status": "success",
                    "type": item_type,
                })
                print(f"  OK [{pub_date_str}] {item_type}: {title[:70]}")
            
            feed_ok = len(results) > 0
            print(f"  → RSS done, {len(results)} items in 3-day window")
        except Exception as e:
            print(f"  → feedparser error: {e}")
            results = []
    else:
        print("  → curl failed")
        results = []
except Exception as e:
    print(f"  → RSS error: {e}")
    results = []

# ─── Step 2: Browser fallback ────────────────────────────────────────────────
if len(results) == 0:
    print("\n[Step 2] Trying Playwright Chromium browser...")
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Navigate to main page
            page.goto("https://frootsmag.com/", timeout=15000)
            time.sleep(1)
            
            # Check for cookie banner
            try:
                accept_btn = page.get_by_text("Accept").first
                if accept_btn:
                    accept_btn.click()
                    print("  → Clicked Accept")
                    time.sleep(1)
            except:
                pass
            
            # Go to reviews category
            try:
                page.goto("https://frootsmag.com/category/reviews/", timeout=15000)
                time.sleep(2)
            except Exception as e:
                print(f"  → navigation error: {e}")
            
            # Scrape up to MAX_PAGES
            all_items = []
            
            for page_num in range(1, MAX_PAGES + 1):
                print(f"\n  -- Page {page_num} --")
                
                try:
                    # Get all article cards
                    articles = page.query_selector_all('article.post, .post, .review-item')
                    print(f"    found {len(articles)} articles")
                    
                    for article in articles:
                        try:
                            # Title
                            title_el = article.query_selector('h2 a, h3 a, .entry-title a')
                            if not title_el:
                                continue
                            title = title_el.inner_text().strip()
                            
                            if MUSIC_EXCLUDE_RE.search(title):
                                print(f"    SKIP: {title[:60]}")
                                continue
                            
                            # URL
                            link_el = title_el if title_el else article.query_selector('a')
                            url = link_el.get_attribute('href') if link_el else ''
                            
                            # Date
                            date_el = article.query_selector('time, .date, .published, [class*="date"]')
                            pub_date_str = None
                            if date_el:
                                date_str = date_el.inner_text().strip()
                                for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d"]:
                                    try:
                                        d = datetime.strptime(date_str, fmt)
                                        pub_date_str = d.strftime("%Y-%m-%d")
                                        break
                                    except:
                                        pass
                            
                            # Check cutoff
                            if pub_date_str:
                                try:
                                    pd = datetime.strptime(pub_date_str, "%Y-%m-%d")
                                    if pd < cutoff:
                                        print(f"    SKIP old: {title[:60]}")
                                        continue
                                except:
                                    pass
                            
                            # Score
                            score_el = article.query_selector('.score, [class*="score"], .rating')
                            score = None
                            if score_el:
                                score_text = score_el.inner_text()
                                m = re.search(r'\d+\.?\d*', score_text)
                                if m:
                                    score = float(m.group())
                            
                            # Excerpt
                            excerpt_el = article.query_selector('.excerpt, .summary, .entry-content')
                            excerpt = ""
                            if excerpt_el:
                                excerpt = re.sub(r'<[^>]+>', '', excerpt_el.inner_text()).strip()[:500]
                            
                            # Type
                            title_lower = title.lower()
                            if any(k in title_lower for k in ['interview', 'feature', 'spotlight', 'profile']):
                                item_type = "feature"
                            else:
                                item_type = "review"
                            
                            all_items.append({
                                "album": title,
                                "artist": "",
                                "score": score,
                                "url": url,
                                "source": "frootsmag.com",
                                "pub_date": pub_date_str or "",
                                "tags": [],
                                "excerpt": excerpt,
                                "site_id": "froots",
                                "crawl_status": "success",
                                "type": item_type,
                            })
                            print(f"    OK: {title[:70]}")
                        except Exception as e:
                            print(f"    article parse error: {e}")
                            continue
                    
                    # Next page
                    if page_num < MAX_PAGES:
                        try:
                            next_btn = page.get_by_text("Next").first
                            if next_btn:
                                next_btn.click()
                                time.sleep(2)
                            else:
                                break
                        except:
                            break
                            
                except Exception as e:
                    print(f"  page scrape error: {e}")
                    break
            
            browser.close()
            
            if all_items:
                results = all_items
                print(f"\n  → Browser scraped {len(results)} items")
            else:
                print("  → Browser returned no items")
                
    except Exception as e:
        print(f"  → Browser error: {e}")
        import traceback
        traceback.print_exc()

# ─── Step 3: Write output ─────────────────────────────────────────────────────
print(f"\n[Step 3] Writing {len(results)} results to {OUTPUT_FILE}")
with open(OUTPUT_FILE, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"Done. {len(results)} items written.")
print(json.dumps({"site": "froots", "count": len(results), "days_scanned": str(CUTOFF_DAYS)}, indent=2))