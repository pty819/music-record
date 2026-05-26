from playwright.sync_api import sync_playwright
from pathlib import Path

WORKSPACE = Path("/home/liyifan/music-record/2026/05/2026-05-25")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://mixmag.asia/category/reviews", timeout=20000)
    page.wait_for_timeout(3000)

    for selector in ["#onetrust-accept-btn-handler", "[aria-label='Accept']", "button:has-text('Accept')"]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(1000)
                print("clicked cookie accept")
                break
        except Exception:
            pass

    page.wait_for_timeout(2000)
    page.screenshot(path=str(WORKSPACE / "mixmag_asia_debug.png"), full_page=True)
    print("screenshot saved")

    html = page.content()
    with open(WORKSPACE / "mixmag_asia_debug.html", "w") as f:
        f.write(html)
    print(f"HTML saved, length={len(html)}")

    print("\n--- body text snippet ---")
    body = page.locator("body").inner_text()[:500]
    print(body[:500])

    browser.close()
