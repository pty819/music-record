#!/usr/bin/env python3
"""Mixmag Asia - full scraper with Playwright. Loads listing, cookie, extracts articles."""
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


def check_cookie(page):
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


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    for fmt in ["%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%d/%m/%Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except Exception:
            pass
    return None


def parse_articles(html):
    """Parse story-block articles from Mixmag Asia HTML."""
    records = []
    seen = set()

    # Match article blocks
    blob_pat = re.compile(
        r'<article class="story-block(?: story-block--\w+)* "[^>]*>(.*?)</article>',
        re.DOTALL
    )
    href_pat = re.compile(r'href="(/read/[^"]+)"')
    title_pat = re.compile(r'<h3 class="story-block__title"[^>]*>(.*?)</h3>')
    excerpt_pat = re.compile(
        r'<p[^>]*class="story-block__excerpt"[^>]*>.*?<p>(.*?)</p>',
        re.DOTALL
    )

    for blob in blob_pat.findall(html):
        href_m = href_pat.search(blob)
        if not href_m:
            continue
        href = href_m.group(1)
        url = f"https://mixmag.asia{href}"

        if url in seen:
            continue
        seen.add(url)

        title_m = title_pat.search(blob)
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

        excerpt_m = excerpt_pat.search(blob)
        excerpt = re.sub(r"<[^>]+>", "", excerpt_m.group(1)).strip() if excerpt_m else ""
        excerpt = excerpt[:500]

        # deck is artist info
        deck_pat = re.compile(
            r'<p[^>]*class="story-block__excerpt"[^>]*>.*?<p>(.*?)</p>',
            re.DOTALL
        )
        deck_m = deck_pat.search(blob)
        deck = re.sub(r"<[^>]+>", "", deck_m.group(1)).strip() if deck_m else ""

        # Score: look for "X/10" anywhere in blob
        score_m = re.search(r"(\d[\d.]*)\s*/\s*10", blob)
        score = float(score_m.group(1)) if score_m else None

        # Date: look for data-date attribute on the article or date text
        date_m = re.search(r'data-date="([^"]+)"', blob)
        if not date_m:
            date_m = re.search(r'<span[^>]*class="story-block__date[^"]*"[^>]*>([^<]+)</span>', blob)

        if date_m:
            pub_date = parse_date(date_m.group(1))
        else:
            pub_date = None

        record = {
            "album": title,
            "artist": deck,
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
    all_records = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(20000)

        # Try up to 2 pages (though pagination may be fake/infinite scroll)
        for page_num in range(1, 3):
            url = ("https://mixmag.asia/music/reviews?page="
                   f"{page_num}" if page_num > 1 else "https://mixmag.asia/music/reviews")
            print(f"[page {page_num}] {url}")

            resp = page.goto(url, timeout=20000)
            print(f"  status: {resp.status}")
            page.wait_for_timeout(3000)
            check_cookie(page)
            page.wait_for_timeout(2000)

            articles = page.locator("article.story-block")
            n = articles.count()
            print(f"  article blocks: {n}")

            html = page.content()

            records = parse_articles(html)
            print(f"  parsed {len(records)} articles")

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
                            print(f"  [date cutoff] {rec['pub_date']}, stopping")
                            cutoff_hit = True
                            break
                    except Exception:
                        pass

                if is_excluded(rec):
                    print(f"  [exclude] {rec['album'][:50]}")
                else:
                    all_records.append(rec)
                    print(f"  [+] {rec['album'][:55]} score={rec['score']} date={rec['pub_date']}")

            if cutoff_hit or n == 0:
                break

            # Check if page 2 is different from page 1 (pagination check)
            if page_num == 1:
                first_url = all_records[0]["url"] if all_records else ""

        browser.close()

    print(f"\nTotal: {len(all_records)}")
    with open(OUTPUT, "w") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}")
    return all_records


if __name__ == "__main__":
    main()