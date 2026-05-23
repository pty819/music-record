#!/usr/bin/env python3
"""Scrape New Music Buff - Playwright Chromium listing + article extraction"""
import asyncio, json, re, sys
from datetime import datetime, timedelta, timezone

async def scrape():
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    results = []
    seen_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Go to main page, handle cookie
        await page.goto("https://newmusicbuff.com/", timeout=20000)
        await asyncio.sleep(2)
        
        try:
            btn = page.locator('button:has-text("Accept"), button:has-text("Agree")').first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                print("Cookie accepted", file=sys.stderr)
                await asyncio.sleep(1)
        except:
            pass

        page_num = 1
        article_urls = []

        while page_num <= 2:
            url = "https://newmusicbuff.com/" if page_num == 1 else f"https://newmusicbuff.com/page/{page_num}/"
            print(f"Listing page {page_num}: {url}", file=sys.stderr)
            
            try:
                await page.goto(url, timeout=20000)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"List page {page_num} failed: {e}", file=sys.stderr)
                break

            articles = await page.locator('article').all()
            print(f"  {len(articles)} articles", file=sys.stderr)
            
            found_on_page = 0

            for art in articles:
                try:
                    link = art.locator('a').first
                    href = await link.get_attribute('href') if link else None
                    if not href or href in seen_urls:
                        continue
                    
                    title_el = art.locator('h2, h3, .entry-title').first
                    title = await title_el.text_content() if title_el else None
                    text = await art.text_content() or ""
                    
                    date_str = None
                    time_el = art.locator('time').first
                    if time_el:
                        date_str = await time_el.get_attribute('datetime')
                    
                    # Skip non-music
                    if re.search(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', text, re.I):
                        print(f"  SKIP(non-music): {title[:50] if title else href}", file=sys.stderr)
                        continue
                    
                    seen_urls.add(href)
                    
                    in_window = True
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                            in_window = dt >= cutoff
                        except:
                            pass
                    
                    print(f"  {'+' if in_window else 'x'} {title[:70] if title else 'N/A'} | {date_str}", file=sys.stderr)
                    
                    if in_window:
                        article_urls.append({
                            "url": href,
                            "title": title.strip() if title else None,
                            "date": date_str,
                        })
                        found_on_page += 1
                except Exception as e:
                    print(f"  art error: {e}", file=sys.stderr)

            if found_on_page == 0:
                print("  No in-window articles, stopping", file=sys.stderr)
                break

            page_num += 1

        print(f"\nIn-window articles: {len(article_urls)}", file=sys.stderr)

        # Visit each in-window article
        for art_info in article_urls:
            url = art_info["url"]
            print(f"\nVisiting: {url}", file=sys.stderr)
            
            try:
                await page.goto(url, timeout=20000)
                await asyncio.sleep(2)
                
                content_area = page.locator('.entry-content, .post-content, article .content, main').first
                article_text = await content_area.text_content() if content_area else await page.content()
                article_text = article_text or ""
                
                # Find score
                score = None
                for pat in [r'(\d+\.?\d*)\s*/\s*10', r'(\d+\.?\d*)\s*out of\s*10', r'Rating:\s*(\d+\.?\d*)']:
                    m = re.search(pat, article_text, re.I)
                    if m:
                        score = float(m.group(1))
                        break
                
                title = art_info["title"] or ""
                
                # Parse album/artist from title
                album = None
                artist = None
                m = re.match(r'^(.+?)\s*[-\u2014]\s*(.+)$', title)
                if m:
                    album = m.group(1).strip()
                    artist = m.group(2).strip()
                else:
                    m = re.match(r'^(.+?):\s*(.+)$', title)
                    if m:
                        artist = m.group(1).strip()
                        album = m.group(2).strip()
                
                article_lower = article_text.lower()
                is_feature = any(kw in article_lower for kw in ['interview', 'feature', 'premiere', 'exclusive', 'conversation', 'essay'])
                is_tracklist = any(kw in article_lower for kw in ['tracklist', 'track list', 'track listing', 'songs include'])
                if is_tracklist:
                    doc_type = "tracklist"
                elif is_feature:
                    doc_type = "feature"
                else:
                    doc_type = "review"
                
                excerpt = re.sub(r'<[^>]+>', '', article_text).strip()[:500]
                
                results.append({
                    "album": album,
                    "artist": artist,
                    "score": score,
                    "url": url,
                    "source": "newmusicbuff.com",
                    "pub_date": art_info["date"],
                    "tags": [],
                    "excerpt": excerpt,
                    "site_id": "newmusicbuff",
                    "crawl_status": "success",
                    "type": doc_type
                })
                print(f"  OK: {album} -- {artist} | score={score} | type={doc_type}", file=sys.stderr)
                
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                results.append({
                    "album": None,
                    "artist": None,
                    "score": None,
                    "url": url,
                    "source": "newmusicbuff.com",
                    "pub_date": art_info["date"],
                    "tags": [],
                    "excerpt": "",
                    "site_id": "newmusicbuff",
                    "crawl_status": "blocked",
                    "type": "review"
                })

        await browser.close()

    print(f"\nTotal results: {len(results)}", file=sys.stderr)
    return results

if __name__ == "__main__":
    from playwright.async_api import async_playwright
    results = asyncio.run(scrape())
    output_path = "/home/liyifan/music-record/2026/05/2026-05-24/new_music_buff_reviews.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Written to {output_path}", file=sys.stderr)