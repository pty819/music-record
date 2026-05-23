#!/usr/bin/env python3
import subprocess
result = subprocess.run(["ls", "/home/liyifan/.hermes/profiles/scraper/home/.cache/camoufox/"], capture_output=True, text=True)
print("camoufox cache:", result.stdout, result.stderr)
result = subprocess.run(["which", "firefox"], capture_output=True, text=True)
print("firefox:", result.stdout, result.stderr)
result = subprocess.run(["dpkg", "-l"], capture_output=True, text=True)
lines = [l for l in result.stdout.split("\n") if "firefox" in l.lower() or "chromium" in l.lower()]
print("\n".join(lines[:10]))
try:
    import playwright
    print("playwright:", playwright.__version__)
except ImportError as e:
    print("playwright not found:", e)
try:
    import camoufox
    print("camoufox:", camoufox)
except ImportError as e:
    print("camoufox import error:", e)