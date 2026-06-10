#!/usr/bin/env python3
"""Check failed URLs from roots_world output."""
import json, subprocess, sys

# Read output
with open('/home/liyifan/music-record/2026/06/2026-06-10/roots_world_reviews.json') as f:
    d = json.load(f)

scraped_urls = {i['url'] for i in d['items']}
# These are known article URLs from the listing (27 total)
all_urls = [
    ("interview", "https://rootsworld.com/interview/silkroad-26.shtml"),
    ("review", "https://rootsworld.com/reviews/primitifs-26.shtml"),
    ("review", "https://rootsworld.com/reviews/tinysun-26.shtml"),
    ("review", "https://rootsworld.com/reviews/hole-26.shtml"),
    ("review", "https://rootsworld.com/reviews/cooney-26.shtml"),
    ("review", "https://rootsworld.com/reviews/prism-prayer-26.shtml"),
    ("review", "https://rootsworld.com/reviews/guldganger-26.shtml"),
    ("review", "https://rootsworld.com/reviews/drjohn-26.shtml"),
    ("review", "https://rootsworld.com/reviews/krota-26.shtml"),
    ("review", "https://rootsworld.com/reviews/sosa-26.shtml"),
    ("review", "https://rootsworld.com/reviews/chicago-gunfire-26.shtml"),
    ("review", "https://rootsworld.com/reviews/santtana-26.shtml"),
    ("review", "https://rootsworld.com/reviews/carolina-26.shtml"),
    ("review", "https://rootsworld.com/reviews/solo-diakite-26.shtml"),
    ("review", "https://rootsworld.com/reviews/jane-26.shtml"),
    ("review", "https://rootsworld.com/reviews/cgs-26.shtml"),
    ("review", "https://rootsworld.com/reviews/niku-26.shtml"),
    ("review", "https://rootsworld.com/reviews/songbook-26.shtml"),
    ("review", "https://rootsworld.com/reviews/petrakis-26.shtml"),
    ("review", "https://rootsworld.com/reviews/ka-26.shtml"),
    ("review", "https://rootsworld.com/reviews/makabe-26.shtml"),
    ("review", "https://rootsworld.com/reviews/omicil-26.shtml"),
    ("review", "https://rootsworld.com/reviews/derksen-26.shtml"),
    ("review", "https://rootsworld.com/reviews/wvsnake-25.shtml"),
    ("review", "https://rootsworld.com/reviews/soundbites.shtml"),
]

print("Failed URLs (not in output):")
for t, url in all_urls:
    if url not in scraped_urls:
        print(f"  FAILED: [{t}] {url}")

# Try fetching one failed url to see if it's a curl issue
test_url = "https://rootsworld.com/reviews/hole-26.shtml"
r = subprocess.run(["curl", "-sL", "-A", "Mozilla/5.0 (X11; Linux aarch64; rv:128.0) Gecko/20100101 Firefox/128.0", "-m", "15", test_url], capture_output=True, timeout=20)
print(f"\nTest fetch {test_url}: {len(r.stdout)} bytes, returncode={r.returncode}")
if r.stdout:
    print("First 200 chars:", r.stdout.decode("utf-8", errors="replace")[:200])

# Also try with --http1.1
r2 = subprocess.run(["curl", "-sL", "--http1.1", "-A", "Mozilla/5.0 (X11; Linux aarch64; rv:128.0) Gecko/20100101 Firefox/128.0", "-m", "15", test_url], capture_output=True, timeout=20)
print(f"\nTest fetch with --http1.1: {len(r2.stdout)} bytes, returncode={r2.returncode}")
if r2.stdout:
    print("First 200 chars:", r2.stdout.decode("utf-8", errors="replace")[:200])
