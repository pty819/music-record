from playwright.sync_api import sync_playwright

BASE_URL = "https://www.seaoftranquility.org/category/reviews"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    with browser.new_page() as page:
        print("Navigating to " + BASE_URL + "...")
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        print("URL: " + page.url)
        print("Title: " + page.title())
        
        body_text = page.locator('body').inner_text()
        print("\nBody text (first 1000):\n" + body_text[:1000])
        
        print("\nDivs: " + str(page.locator('div').count()))
        print("Articles: " + str(page.locator('article').count()))
        print("Links total: " + str(page.locator('a').count()))
        
        print("\nButtons:")
        for btn in page.locator('button').all():
            try:
                txt = btn.inner_text().strip()
                if txt:
                    print("  Button: " + txt)
            except:
                pass
        
        print("\ncf-*: " + str(page.locator('[id*="cf"], [class*="cf"]').count()))
        
        page.screenshot(path='sea_of_tranquility_debug.png')
        print("\nScreenshot saved: sea_of_tranquility_debug.png")
        
        html = page.content()
        print("\nHTML length: " + str(len(html)))
        print("HTML (first 2000):\n" + html[:2000])
    
    browser.close()