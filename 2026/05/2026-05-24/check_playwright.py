#!/usr/bin/env python3
import subprocess
result = subprocess.run(["python3", "-m", "playwright", "install", "--dry-run"], capture_output=True, text=True)
print(result.stdout[-2000:] if result.stdout else "")
print(result.stderr[-2000:] if result.stderr else "")
result2 = subprocess.run(["python3", "-c", "from playwright.sync_api import sync_playwright; print('playwright ok')"], capture_output=True, text=True)
print(result2.stdout, result2.stderr)