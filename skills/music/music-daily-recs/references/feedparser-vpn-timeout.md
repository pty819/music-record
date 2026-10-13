# feedparser/urllib Meta VPN Timeout Issue

## Problem
Meta VPN (28.0.0.x routes all traffic) adds ~8-10s TLS handshake overhead per connection.
With `socket.setdefaulttimeout(15)`, most RSS feeds timeout before any data arrives.
Camoufox is unaffected — browser uses persistent/keepalive connections.

## Diagnosis Pattern
```bash
# 1. Check if curl works but Python doesn't
curl -s --max-time 20 "https://daily.bandcamp.com/feed" | wc -c    # OK?
python3 -c "import feedparser; print(len(feedparser.parse('https://daily.bandcamp.com/feed').entries))"  # TIMEOUT?

# 2. Confirm it's TLS overhead, not DNS/routing
python3 -c "
import socket, ssl, time
s = socket.socket(); s.settimeout(10)
t0 = time.time()
s.connect(('28.0.0.35', 443))
print(f'TCP: {time.time()-t0:.1f}s')
ctx = ssl.create_default_context()
t1 = time.time()
ctx.wrap_socket(s, server_hostname='daily.bandcamp.com')
print(f'TLS: {time.time()-t1:.1f}s')
"
# Expected: TCP ~0s, TLS 8-10s

# 3. Test with increased timeout
python3 -c "
import feedparser, socket
socket.setdefaulttimeout(30)
feed = feedparser.parse('https://daily.bandcamp.com/feed')
print(f'entries: {len(feed.entries)}')
"
```

## Fix
In `fast-rss-scrape.py`: `socket.setdefaulttimeout(30)` (was 15).
Terminal timeout for full RSS run: 900s (was 600).

## Observed Timing (2026-06-10)
| Site | Time | Result |
|---|---|---|
| bandcamp_daily | 26.2s | 2 items |
| the_quietus | 28.3s | 12 items |
| side_line | 14.5s | 8 items |
| Full 28-site run | ~12 min | 27 items |

## Key Insight
`curl` and Python `urllib` both go through the same VPN route, but:
- curl uses its own TLS stack (usually OpenSSL with connection pooling)
- Python's feedparser/urllib creates fresh SSL contexts per feed
- Each fresh context = full TLS handshake = 8-10s overhead
