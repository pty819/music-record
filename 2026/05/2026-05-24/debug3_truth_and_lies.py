#!/usr/bin/env python3
import re, sys, time
sys.path.insert(0, '/home/liyifan/.hermes/profiles/scraper/home/.local/lib/python3.11/site_packages')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()

    # Check magazine home page
    page.goto("https://www.truthandliesmusic.com/magazine", timeout=15000)
    time.sleep(3)
    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")

    # Get all article links from magazine page
    links = page.query_selector_all("a")
    print(f"\nAll links on /magazine:")
    for l in links:
        href = l.get_attribute("href") or ""
        text = l.inner_text().strip()[:80]
        if href:
            print(f"  {repr(href)} | {repr(text)}")

    # Check first article for structure
    article_url = "https://www.truthandliesmusic.com/magazine/carol-maia-amp-jeremy-gustin-its-nice-to-see-a-lake-in-your-eyes-hive-mind-records-a-review"
    page.goto(article_url, timeout=15000)
    time.sleep(2)
    print(f"\nArticle URL: {page.url}")

    # Get meta info
    try:
        date_el = page.query_selector("time") or page.query_selector("[class*='date']") or page.query_selector("[class*='published']")
        if date_el:
            print(f"Date element: {date_el.inner_text()} | datetime: {date_el.get_attribute('datetime')}")
    except Exception as e:
        print(f"Date error: {e}")

    # Get score/rating
    try:
        score_el = page.query_selector("[class*='score']") or page.query_selector("[class*='rating']") or page.query_selector("[class*='stars']")
        if score_el:
            print(f"Score: {score_el.inner_text()}")
    except Exception as e:
        print(f"Score error: {e}")

    # Get article content excerpt
    try:
        content = page.query_selector("article") or page.query_selector("[class*='content']") or page.query_selector("[class*='post']")
        if content:
            text = content.inner_text()[:500]
            print(f"Content preview: {repr(text)}")
    except Exception as e:
        print(f"Content error: {e}")

    browser.close()