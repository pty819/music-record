#!/usr/bin/env python3
"""
Scrape RootsWorld album reviews within 3-day window.
Output: roots_world_reviews.json
"""
import json, re, time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

SITE_ID = "roots_world"
BASE_URL = "https://rootsworld.com"
OUT_PATH = "/home/liyifan/music-record/2026/05/2026-05-25/roots_world_reviews.json"
CUTOFF = datetime.utcnow() - timedelta(days=3)

print(f"Cutoff: {CUTOFF.strftime('%Y-%m-%d')}")

results = []

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(date_str[:10], fmt).strftime("%Y-%m-%d")
        except:
            pass
    return None

def resolve_url(href, page_url):
    if not href:
        return ""
    return urljoin(page_url, href)

def fetch_listing(browser, url):
    page = browser.new_page()
    page.set_default_timeout(20000)
    entries = []
    try:
        page.goto(url, timeout=30000)
        time.sleep(2)
        try:
            page.get_by_text("Accept", exact=False).first.click(timeout=2000)
            time.sleep(0.5)
        except:
            pass

        cards = page.query_selector_all("article.review-card")
        print(f"  Found {len(cards)} review cards")
        
        for card in cards:
            links = card.query_selector_all("a")
            title = ""
            href = ""
            for a in links:
                txt = a.text_content().strip()
                if txt and len(txt) > 10 and not txt.startswith("Subscribe"):
                    title = txt
                    href = a.get_attribute("href") or ""
                    break
            
            if title and href:
                resolved = resolve_url(href, url)
                entries.append((title, resolved))
        
        print(f"  Extracted {len(entries)} entries")
            
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
    finally:
        page.close()
    return entries

def fetch_detail(browser, url, list_title):
    """Fetch article page and extract details."""
    page = browser.new_page()
    page.set_default_timeout(20000)
    score = None
    tags = []
    excerpt = ""
    item_type = "review"
    page_title = ""
    artist_name = ""
    album_name = ""
    try:
        page.goto(url, timeout=30000)
        time.sleep(3)  # Wait for JS/iframes

        try:
            page.get_by_text("Accept", exact=False).first.click(timeout=2000)
            time.sleep(0.5)
        except:
            pass

        page_title = page.title()
        
        # Parse JSON-LD structured data for artist/album
        try:
            ld_json = page.query_selector('script[type="application/ld+json"]')
            if ld_json:
                ld_text = ld_json.text_content()
                ld_data = json.loads(ld_text)
                if ld_data.get('@type') == 'Review':
                    item = ld_data.get('itemReviewed', {})
                    if isinstance(item, dict):
                        album_name = item.get('name', '')
                        by_artist = item.get('byArtist', [])
                        if isinstance(by_artist, list) and by_artist:
                            if isinstance(by_artist[0], dict):
                                artist_name = by_artist[0].get('name', '')
                            elif isinstance(by_artist[0], str):
                                artist_name = by_artist[0]
                        elif isinstance(by_artist, dict):
                            artist_name = by_artist.get('name', '')
        except Exception as e:
            print(f"  JSON-LD parse error: {e}")

        # Date
        date_str = None
        date_el = page.query_selector("time")
        if date_el:
            date_str = date_el.get_attribute("datetime") or date_el.text_content().strip()

        # Get body content - article text is in .review-body or .page-wrapper
        body_el = (page.query_selector(".review-body") or
                   page.query_selector(".entry-content") or
                   page.query_selector(".page-wrapper"))
        
        body_text = body_el.text_content()[:4000] if body_el else ""

        # Score
        score_match = re.search(r'(\d+\.?\d*)\s*/\s*(10|5|100)', body_text)
        if score_match:
            score = float(score_match.group(1))
            max_score = float(score_match.group(2))
            if max_score == 5:
                score = score * 2
            elif max_score == 100:
                score = score / 10

        # Tags
        tag_els = page.query_selector_all("[rel='tag'], .tags a, .tag")
        for t in tag_els:
            txt = t.text_content().strip()
            if txt and txt not in tags:
                tags.append(txt)

        # Excerpt: first substantial paragraph
        if body_el:
            paragraphs = body_el.query_selector_all("p")
            for para in paragraphs:
                para_text = strip_html(para.text_content())
                # Skip very short paragraphs (track names, labels, etc.)
                if len(para_text) > 100:
                    excerpt = para_text[:500]
                    break

        url_lower = url.lower()
        if "interview" in url_lower or "feature" in url_lower:
            item_type = "feature"

        print(f"  page_title: {page_title[:80]}")
        print(f"  album: {album_name!r}, artist: {artist_name!r}")
        print(f"  score={score}, excerpt={excerpt[:60]!r}")

    except Exception as e:
        print(f"  Error fetching detail {url}: {e}")
    finally:
        page.close()

    return date_str, score, tags, excerpt, item_type, page_title, artist_name, album_name

# Main
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    all_entries = []
    for page_num in range(1, 3):
        if page_num == 1:
            url = BASE_URL + "/rw/"
        else:
            url = f"{BASE_URL}/rw/?start=20"
        print(f"\nListing page {page_num}: {url}")
        entries = fetch_listing(browser, url)
        
        for title, resolved in entries:
            if resolved not in [e[1] for e in all_entries]:
                all_entries.append((title, resolved))
        
    print(f"\nTotal unique entries: {len(all_entries)}")

    for list_title, href in all_entries:
        full_url = href
        if not full_url.startswith("http"):
            full_url = urljoin(BASE_URL + "/rw/", full_url)
        
        if "racethesky.com" in full_url or "RaceTheSky" in list_title:
            continue
        if "soundbites" in href:
            continue
            
        print(f"\nProcessing: {list_title[:60]}")
        (date_str, score, tags, excerpt, item_type, 
         page_title, artist_name, album_name) = fetch_detail(browser, full_url, list_title)
        
        combined = (list_title + " " + " ".join(tags)).upper()
        if any(x in combined for x in ["(BLU-RAY)", "(UHD)", "(VOD)", "(DVD)"]):
            print(f"  SKIP (non-music): {list_title}")
            continue

        record = {
            "album": album_name,
            "artist": artist_name,
            "score": score,
            "url": full_url,
            "source": BASE_URL,
            "pub_date": parse_date(date_str) if date_str else None,
            "tags": [t for t in tags if t is not None],
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": item_type,
        }
        results.append(record)
        print(f"  -> Added: {artist_name[:30]} - {album_name[:40]}, type={item_type}")

    browser.close()

# Write output
with open(OUT_PATH, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\nDone. Wrote {len(results)} items to {OUT_PATH}")
print(json.dumps({"site": SITE_ID, "count": len(results), "cutoff": CUTOFF.strftime("%Y-%m-%d")}, indent=2))