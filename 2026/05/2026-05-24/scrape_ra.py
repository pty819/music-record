import json, re
from datetime import datetime, timedelta
from camoufox.sync_api import Camoufox

OUTPUT = "/home/liyifan/music-record/2026/05/2026-05-24/resident_advisor_reviews.json"
CUTOFF = (datetime.utcnow() - timedelta(days=3)).timestamp()
SEEN = set()

def strip_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    import html as html_module
    text = html_module.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_ra_items(page, item_type="review"):
    results = []
    
    # Try multiple selectors since RA structure varies
    selectors = [
        "article",
        ".review-card",
        ".article-card",
        ".item",
        "[class*='review']",
        ".listing-item",
    ]
    
    cards = []
    for sel in selectors:
        cards = page.query_selector_all(sel)
        if cards:
            print(f"  Selector '{sel}' found {len(cards)} cards")
            break
    
    for card in cards:
        try:
            a_tag = card.query_selector('a')
            if not a_tag:
                continue
            href = a_tag.get_attribute('href') or ""
            if not href:
                continue
            if not href.startswith('http'):
                href = "https://ra.co" + href
            
            # Skip non-review links
            if '/reviews/' not in href and '/features/' not in href:
                continue
            
            title = a_tag.inner_text().strip()
            
            # Extract artist/album from title
            artist = ""
            album = ""
            if '–' in title:
                parts = title.split('–', 1)
                artist = parts[0].strip()
                album = parts[1].strip()
            elif '-' in title:
                parts = title.split('-', 1)
                artist = parts[0].strip()
                album = parts[1].strip()
            
            # Score
            score = None
            score_el = card.query_selector('[class*="score"]') or card.query_selector('.rating') or card.query_selector('[class*="rating"]')
            if score_el:
                score_text = score_el.inner_text().strip()
                try:
                    score = float(score_text)
                except:
                    score = None
            
            # Date
            date_str = ""
            pub_ts = None
            time_el = card.query_selector('time') or card.query_selector('[class*="date"]') or card.query_selector('[class*="time"]')
            if time_el:
                date_str = time_el.get_attribute('datetime') or time_el.inner_text().strip()
                if date_str:
                    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d %b %Y", "%B %d, %Y"):
                        try:
                            pub_ts = datetime.strptime(date_str[:19], fmt).timestamp()
                            break
                        except:
                            pass
            
            # Excerpt
            excerpt = ""
            for sel in ['[class*="excerpt"]', '[class*="summary"]', 'p', '.desc']:
                el = card.query_selector(sel)
                if el:
                    excerpt = strip_html(el.inner_text())[:500]
                    break
            
            if href in SEEN:
                continue
            SEEN.add(href)
            
            if pub_ts and pub_ts < CUTOFF:
                continue
            
            if any(x in title.upper() for x in ["BLU-RAY", "UHD", "VOD", "DVD"]):
                print(f"  Skipping non-music: {title}")
                continue
            
            results.append({
                "album": album,
                "artist": artist,
                "score": score,
                "url": href,
                "source": "Resident Advisor",
                "pub_date": date_str,
                "tags": [],
                "excerpt": excerpt,
                "site_id": "resident_advisor",
                "crawl_status": "success",
                "type": item_type,
            })
        except Exception as e:
            print(f"  Card error: {e}")
    
    return results

def main():
    print("Starting camoufox browser...")
    with Camoufox(headless=True) as browser:
        page = browser.new_page()
        
        # Initial visit
        print("Navigating to ra.co/reviews...")
        try:
            page.goto("https://ra.co/reviews", timeout=30000)
        except Exception as e:
            print(f"Initial load error: {e}")
            with open("/tmp/ra_debug.html", "w") as f:
                f.write(page.content())
            print("Saved page content to /tmp/ra_debug.html")
            browser.close()
            return 0
        
        page.wait_for_timeout(3000)
        
        # Cookie wall
        try:
            for text in ["Accept", "Agree", "OK", "Continue"]:
                btns = page.get_by_text(text)
                if btns.count() > 0:
                    print(f"Clicking '{text}' button")
                    btns.first.click()
                    page.wait_for_timeout(2000)
                    break
        except Exception as e:
            print(f"Cookie button error: {e}")
        
        # Check if blocked
        if "blocked" in page.title().lower() or "attention" in page.title().lower():
            print(f"BLOCKED: {page.title()}")
            with open("/tmp/ra_blocked.html", "w") as f:
                f.write(page.content())
            browser.close()
            return 0
        
        print(f"Page title: {page.title()}")
        
        all_items = []
        
        # Try reviews pages
        for pg in range(1, 3):
            url = f"https://ra.co/reviews?page={pg}"
            print(f"\nVisiting {url}")
            try:
                page.goto(url, timeout=30000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Error: {e}")
                break
            
            if "blocked" in page.title().lower():
                print("BLOCKED on this page")
                break
            
            items = extract_ra_items(page, "review")
            print(f"  Found {len(items)} review items on page {pg}")
            all_items.extend(items)
            
            if not items:
                break
        
        # Try features pages
        print("\nChecking features page...")
        for pg in range(1, 3):
            url = f"https://ra.co/features?page={pg}"
            print(f"\nVisiting {url}")
            try:
                page.goto(url, timeout=30000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Error: {e}")
                break
            
            if "blocked" in page.title().lower():
                print("BLOCKED on features")
                break
            
            items = extract_ra_items(page, "feature")
            print(f"  Found {len(items)} feature items on page {pg}")
            for item in items:
                item["score"] = None
            all_items.extend(items)
            
            if not items:
                break
        
        browser.close()
    
    # Dedup
    seen_urls = set()
    final = []
    for item in all_items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            final.append(item)
    
    print(f"\nTotal unique items: {len(final)}")
    
    with open(OUTPUT, "w") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)
    
    print(f"Written to {OUTPUT}")
    return len(final)

if __name__ == "__main__":
    n = main()
    print(f"DONE: {n} items")