#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    page = browser.new_page()
    print('launching...')
    try:
        page.goto('https://www.jazztimes.com', wait_until='domcontentloaded', timeout=45000)
        print('loaded, title:', page.title())
    except Exception as e:
        print('error:', e)
    browser.close()