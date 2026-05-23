#!/usr/bin/env python3
"""Test Sequenza21 - inspect article structure."""
from playwright.sync_api import sync_playwright
import json

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        resp = page.goto('https://www.sequenza21.com/', timeout=15000, wait_until='load')
        page.wait_for_timeout(3000)
        
        # Click cookie accept
        for text in ['Accept', 'Agree', 'Consent']:
            try:
                btn = page.locator(f'text={text}').first
                if btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(1000)
                    break
            except:
                pass
        
        articles = page.query_selector_all("article")
        print(f'Found {len(articles)} articles\n')
        
        for i, a in enumerate(articles):
            print(f"--- Article {i+1} ---")
            h = a.query_selector("h2, h3")
            title = h.inner_text().strip() if h else "(no title)"
            print(f"Title: {title}")
            
            # Get all links
            links = a.query_selector_all("a[href]")
            for link in links[:3]:
                href = link.get_attribute("href") or ""
                txt = link.inner_text().strip()[:40]
                if href:
                    print(f"  Link: {txt} -> {href}")
            
            # Get date
            time_el = a.query_selector("time")
            if time_el:
                dt = time_el.get_attribute("datetime") or time_el.inner_text().strip()
                print(f"  Date: {dt}")
            
            # Get categories/tags
            cats = a.query_selector_all("[class*='cat'], [class*='tag'], .categories")
            for c in cats:
                print(f"  Cat: {c.inner_text().strip()[:60]}")
            
            # Get excerpt
            ex = a.query_selector(".excerpt, .summary, .entry-summary, .post-excerpt, p")
            if ex:
                txt = ex.inner_text().strip()[:100]
                print(f"  Excerpt: {txt}")
            
            print()
        
        # Try to find Older posts link
        all_links = page.query_selector_all("a")
        for link in all_links:
            text = link.inner_text().strip()
            href = link.get_attribute("href") or ""
            if any(x in text for x in ["Older", "Next", "»", ">>"]) and href:
                print(f"Nav link: '{text}' -> {href}")
        
    except Exception as e:
        print('error:', e)
        import traceback
        traceback.print_exc()
    browser.close()