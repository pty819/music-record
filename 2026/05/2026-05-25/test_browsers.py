#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import json

print("Testing playwright Firefox...")
try:
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        print("Firefox launched OK")
        browser.close()
except Exception as e:
    print(f"Firefox failed: {e}")

print("\nTesting playwright Chromium...")
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        print("Chromium launched OK")
        browser.close()
except Exception as e:
    print(f"Chromium failed: {e}")