from playwright.sync_api import sync_playwright
import re

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    with browser.new_page() as page:
        page.goto("https://www.seaoftranquility.org/reviews.php", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)
        html = page.content()
        
        whole_count = len(re.findall("newgreen", html))
        blue_count = len(re.findall("newblue", html))
        print("newgreen count:", whole_count)
        print("newblue count:", blue_count)
        
        # Find all review links with newgreen (last 3 days)
        pattern = re.compile(r'<a href="(reviews\.php\?op=showcontent&amp;id=\d+)">([^<]+)\s*<img src="images/newgreen\.gif"')
        new_items = list(pattern.finditer(html))
        print("\nNew green items (within 3 days):")
        for m in new_items[:20]:
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            title = re.sub(r'\s+', ' ', title).strip()
            print(f"  {m.group(1)} | {title}")
    browser.close()