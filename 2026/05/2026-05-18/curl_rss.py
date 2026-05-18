import subprocess
import json
import re
from datetime import datetime, timedelta
import sys

# Try curl to fetch RSS (which worked before)
result = subprocess.run([
    'curl', '-s', '-L', '--max-time', '30',
    '-H', 'User-Agent: Mozilla/5.0',
    'https://www.thewire.co.uk/rss'
], capture_output=True, text=True, timeout=40)

print('curl exit:', result.returncode)
print('stdout len:', len(result.stdout))
print('First 800:', result.stdout[:800])
print()

# Try with cookie
result2 = subprocess.run([
    'curl', '-s', '-L', '--max-time', '30',
    '-H', 'User-Agent: Mozilla/5.0',
    '-H', 'Cookie: CookieConsent=1',
    'https://www.thewire.co.uk/rss'
], capture_output=True, text=True, timeout=40)

print('curl with cookie exit:', result2.returncode)
print('First 800:', result2.stdout[:800])