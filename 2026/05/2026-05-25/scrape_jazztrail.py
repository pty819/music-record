#!/usr/bin/env python3
"""
Scrape JazzTrail album reviews within 3-day window.
Output: jazz_trail_reviews.json
"""
import json, re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import time

SITE_ID = "jazz_trail"
BASE_URL = "https://jazztrail.net"
OUT_PATH = "/home/liyifan/music-record/2026/05/2026-05-25/jazz_trail_reviews.json"
CUTOFF = datetime.utcnow() - timedelta(days=3)

print(f"Cutoff: {CUTOFF.strftime('%Y-%m-%d')}")

results = []

def strip_html(text):
    """Remove HTML tags and normalize whitespace."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_date(date_str):
    """Parse date string to YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(date_str[:10] if '-' in date_str else date_str, fmt).strftime("%Y-%m-%d")
        except:
            pass
    return None

def fetch_listing(browser, url):
    """Fetch a blog listing page and return list of (title, href, date_str)."""
    page = browser.new_page()
    page.set_default_timeout(15000)
    entries = []
    try:
        page.goto(url, timeout=20000)
        time.sleep(1)
        
        # Accept cookies
        try:
            page.get_by_text("Accept", exact=False).first.click(timeout=1500)
            time.sleep(0.5)
        except:
            pass
        
        articles = page.query_selector_all("article")
        for art in articles:
            title_el = art.query_selector("h1.entry-title a")
            if not title_el:
                continue
            title = title_el.text_content().strip()
            href = title_el.get_attribute("href") or ""
            
            date_el = art.query_selector("time.published")
            date_str = date_el.get_attribute("datetime") if date_el else ""
            
            entries.append((title, href, date_str))
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
    finally:
        page.close()
    return entries

def fetch_detail(browser, url, title):
    """Fetch detail page and extract score, tags, excerpt."""
    page = browser.new_page()
    page.set_default_timeout(15000)
    score = None
    tags = []
    excerpt = ""
    try:
        page.goto(url, timeout=20000)
        time.sleep(1)
        
        try:
            page.get_by_text("Accept", exact=False).first.click(timeout=1500)
            time.sleep(0.5)
        except:
            pass
        
        # Get body text
        body_el = page.query_selector(".entry-content, .post-body, article .content")
        body_text = body_el.text_content()[:3000] if body_el else ""
        
        # Score: look for X/10 pattern
        score_match = re.search(r'(\d+\.?\d*)\s*/\s*10', body_text)
        if score_match:
            score = float(score_match.group(1))
        
        # Tags
        tag_els = page.query_selector_all(".tags a, [rel=tag], .tag")
        for t in tag_els:
            txt = t.text_content().strip()
            if txt and txt not in tags:
                tags.append(txt)
        
        # Excerpt: first paragraph of body
        if body_el:
            first_p = body_el.query_selector("p")
            if first_p:
                excerpt = strip_html(first_p.text_content)[:500]
        
        print(f"  Detail: score={score}, tags={tags[:3]}")
        
    except Exception as e:
        print(f"  Error fetching detail {url}: {e}")
    finally:
        page.close()
    
    return score, tags, excerpt

# Main
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    
    # Scrape pages 1 and 2
    all_entries = []
    for page_num in range(1, 3):
        url = f"{BASE_URL}/blog" if page_num == 1 else f"{BASE_URL}/blog?page={page_num}"
        print(f"Listing page {page_num}...")
        entries = fetch_listing(browser, url)
        print(f"  Found {len(entries)} entries")
        all_entries.extend(entries)
    
    # Filter by date window
    in_window = []
    for title, href, date_str in all_entries:
        dt = None
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        except:
            pass
        
        if dt and dt >= CUTOFF:
            in_window.append((title, href, date_str))
            print(f"  IN WINDOW: {date_str}: {title[:60]}")
    
    print(f"\nEntries in window: {len(in_window)}")
    
    # For each in-window entry, fetch detail
    for title, href, date_str in in_window:
        full_url = BASE_URL + href if href.startswith("/") else href
        print(f"\nProcessing: {title[:60]}")
        
        score, tags, excerpt = fetch_detail(browser, full_url, title)
        
        # Non-music filter (BLU-RAY, UHD, VOD, DVD)
        combined = (title + " ".join(tags)).upper()
        if any(x in combined for x in ["(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)"]):
            print(f"  SKIP (non-music): {title}")
            continue
        
        # Determine type: feature if no score (interview/review) or tracklist
        item_type = "review"
        if score is None:
            if "interview" in href.lower() or "feature" in href.lower():
                item_type = "feature"
        
        record = {
            "album": title,
            "artist": "",  # Artist is usually part of album title
            "score": score,
            "url": full_url,
            "source": BASE_URL,
            "pub_date": parse_date(date_str),
            "tags": tags,
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": item_type,
        }
        results.append(record)
        print(f"  -> Added: {title[:50]}, type={item_type}")
    
    browser.close()

# Write output
with open(OUT_PATH, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\nDone. Wrote {len(results)} items to {OUT_PATH}")
print(json.dumps({"site": SITE_ID, "count": len(results), "cutoff": CUTOFF.strftime("%Y-%m-%d")}, indent=2))