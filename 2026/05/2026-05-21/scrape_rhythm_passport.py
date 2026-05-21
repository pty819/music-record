from playwright.sync_api import sync_playwright
import json, re
from datetime import datetime, timedelta

three_days_ago = datetime.now() - timedelta(days=3)
print('Three days ago:', three_days_ago)

results = []

with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    page = browser.new_page()
    page.goto('https://rhythmpassport.com/', timeout=30000)
    page.wait_for_load_state('networkidle', timeout=15000)
    
    # Check for cookie banner
    try:
        agree_btn = page.get_by_text(re.compile(r'(agree|accept|i agree)', re.I)).first
        agree_btn.click()
        page.wait_for_timeout(1000)
        print('Clicked cookie agree')
    except Exception as e:
        print(f'No cookie banner: {e}')
    
    print('Page title:', page.title())
    
    # Find article links on homepage
    articles = page.query_selector_all('article, .post, .review-item, h2 a, h3 a')
    print(f'Found {len(articles)} article elements')
    
    for a in articles[:20]:
        try:
            href = a.get_attribute('href')
            text = a.inner_text()[:200]
            print(f'Link: {href} | Text: {text[:100]}')
        except:
            pass
    
    browser.close()
