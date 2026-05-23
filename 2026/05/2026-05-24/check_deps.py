#!/usr/bin/env python3
import subprocess
result = subprocess.run(["python3", "-c", "import feedparser; print('feedparser ok')"], capture_output=True, text=True)
print("feedparser:", result.stdout.strip(), result.stderr.strip())

result = subprocess.run(["python3", "-c", "import camoufox; print('camoufox ok')"], capture_output=True, text=True)
print("camoufox:", result.stdout.strip(), result.stderr.strip())

result = subprocess.run(["python3", "-c", "import playwright; print('playwright ok')"], capture_output=True, text=True)
print("playwright:", result.stdout.strip(), result.stderr.strip())