#!/usr/bin/env python3
"""Get page 2 of Mixmag Asia reviews, parse from HTML."""
from playwright.sync_api import sync_playwright
from pathlib import Path
import json, re
from datetime import datetime, timedelta

WORKSPACE = Path("/home/liyifan/music-record/2026/05/2026-05-25")
OUTPUT = WORKSPACE / "mixmag_asia_reviews.json"
SITE_ID = "mixmag_asia"
SOURCE = "Mixmag Asia"
CUTOFF_DAYS = 3
cutoff = datetime.now() - timedelta(days=CUTOFF_DAYS)
EXCLUDES = ["BLU-RAY", "UHD", "VOD", "DVD"]
EXCLUDE_RE = re.compile("|".join(EXCLUDES), re.IGNORECASE)

def parse_date(text):
    if not text:
        return None
    text = text.strip()
    for fmt in ["%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except Exception:
            pass
    return None

def parse_articles_from_html(html):
    records = []
    article_pattern = re.compile(r'<article[^>]*class="story-block[^"]*"[^>]*>(.*?)</article>', re.DOTALL)
    matches = article_pattern.findall(html)
    
    for blob in matches:
        href_m = re.search(r'<a[^>]+href="(/read/[^"]+)"', blob)
        if not href_m:
            continue
        href = href_m.group(1)
        if "/read/" not in href:
            continue
        
        # title
        title_m = re.search(r'<h2[^>]*>(.*?)</h2>', blob, re.DOTALL)
        if not title_m:
            title_m = re.search(r'<h3[^>]*>(.*?)</h3>', blob, re.DOTALL)
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
        
        # deck
        deck_m = re.search(r'<p[^>]*class="story-block__deck[^"]*"[^>]*>(.*?)</p>', blob, re.DOTALL)
        if not deck_m:
            deck_m = re.search(r'<p[^>]*class="story-block__subheading[^"]*"[^>]*>(.*?)</p>', blob, re.DOTALL)
        deck = re.sub(r"<[^>]+>", "", deck_m.group(1)).strip() if deck_m else ""
        
        # date
        date_m = re.search(r'<time[^>]*>(.*?)</time>', blob, re.DOTALL)
        if not date_m:
            date_m = re.search(r'<span[^>]*class="story-block__date[^"]*"[^>]*>(.*?)</span>', blob, re.DOTALL)
        date_str = date_m.group(1).strip() if date_m else ""
        pub_date = parse_date(date_str)
        
        # score
        score_m = re.search(r'(\d[\d.]*)\s*/\s*10', blob)
        score = float(score_m.group(1)) if score_m else None
        
        url = f"https://mixmag.asia{href}" if href.startswith("/") else href
        album = title
        artist = deck
        excerpt = deck[:500]
        
        record = {
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": [],
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "ok",
            "type": "review" if score is not None else "feature",
        }
        
        records.append(record)
    
    return records

def is_excluded(record):
    text = (record.get("album") or "") + (record.get("excerpt") or "")
    return bool(EXCLUDE_RE.search(text))

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20000)
        
        all_records = []
        seen = set()
        
        for page_num in range(1, 3):
            url = f"https://mixmag.asia/music/reviews?page={page_num}" if page_num > 1 else "https://mixmag.asia/music/reviews"
            print(f"[page {page_num}] {url}")
            
            resp = page.goto(url, timeout=20000)
            print(f"  status: {resp.status}")
            page.wait_for_timeout(3000)
            
            # Cookie wall
            for sel in ["#onetrust-accept-btn-handler", "[aria-label='Accept']", "button:has-text('Accept')"]:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        page.wait_for_timeout(1000)
                        print("  cookie accept clicked")
                        break
                except Exception:
                    pass
            
            # Save HTML for parsing
            html = page.content()
            with open(WORKSPACE / f"mixmag_asia_page{page_num}.html", "w") as f:
                f.write(html)
            
            records = parse_articles_from_html(html)
            print(f"  found {len(records)} articles")
            
            cutoff_hit = False
            for rec in records:
                if rec["url"] in seen:
                    continue
                seen.add(rec["url"])
                
                # date filter
                if rec["pub_date"]:
                    try:
                        pub = datetime.fromisoformat(rec["pub_date"])
                        if pub < cutoff:
                            print(f"  [date filter] cutoff at {rec['pub_date']}, stopping")
                            cutoff_hit = True
                            break
                    except Exception:
                        pass
                
                if is_excluded(rec):
                    print(f"  [exclude] {rec['album'][:50]}")
                else:
                    all_records.append(rec)
                    print(f"  [+] {rec['album'][:55]} score={rec['score']} date={rec['pub_date']}")
            
            if cutoff_hit:
                break
            
            if not records:
                break
            
            browser.close()
    
    # Load page 1 HTML too if we didn't get it
    p1_path = WORKSPACE / "mixmag_asia_reviews_page.html"
    if p1_path.exists():
        with open(p1_path) as f:
            html1 = f.read()
        records_p1 = parse_articles_from_html(html1)
        print(f"\nPage 1 had {len(records_p1)} articles")
    
    print(f"\nTotal unique: {len(all_records)}")
    
    with open(OUTPUT, "w") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}")

if __name__ == "__main__":
    main()