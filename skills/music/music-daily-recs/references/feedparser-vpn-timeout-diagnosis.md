# feedparser/urllib VPN Timeout Diagnosis

## Symptom
RSS scraper returns 0 items for ALL sites. Camoufox workers succeed on the same machine at the same time.

## Root Cause
Meta VPN (28.0.0.x) adds ~8-10s TLS handshake overhead per new HTTPS connection. `socket.setdefaulttimeout(15)` leaves <5s for data transfer — most sites timeout before any data arrives. Camoufox is unaffected because it's a long-lived browser process with persistent/reused connections.

## Diagnosis Steps

### 1. Confirm curl works but Python doesn't
```bash
# curl uses its own TLS stack, often succeeds
curl -s --max-time 20 "https://daily.bandcamp.com/feed" | wc -c

# Python urllib uses system OpenSSL, fails
python3 -c "
import urllib.request, socket
socket.setdefaulttimeout(15)
req = urllib.request.Request('https://daily.bandcamp.com/feed', headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=15)
print(len(resp.read()))
"
```

### 2. Measure TLS handshake time
```python
import socket, ssl, time
host = 'daily.bandcamp.com'
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
t0 = time.time()
s.connect((host, 443))  # should be instant via VPN
ctx = ssl.create_default_context()
ss = ctx.wrap_socket(s, server_hostname=host)
print(f'TLS handshake: {time.time()-t0:.1f}s')  # expect 8-10s on Meta VPN
ss.close()
```

### 3. Verify feedparser works with longer timeout
```python
import feedparser, socket
socket.setdefaulttimeout(30)  # was 15
feed = feedparser.parse('https://daily.bandcamp.com/feed')
print(f'entries: {len(feed.entries)}')  # should be 30+ now
```

### 4. Check routing
```bash
ip route get 8.8.8.8        # should NOT show 28.0.0.x unless VPN is primary
ip route get 28.0.0.35      # Meta VPN interface
```

## Fix
- `socket.setdefaulttimeout(30)` in `fast-rss-scrape.py`
- Terminal timeout: 900s (28 sites × 30s worst case = 840s + margin)

## Why 30s and not higher
- 30s gives 20s for data after 10s TLS handshake — enough for RSS XML
- Higher values (45s) would push total runtime past 15 minutes
- Sites that timeout at 30s are genuinely unreachable (not just slow)

## Per-site timing (VPN, 30s timeout)
| Speed tier | Sites | Typical time |
|---|---|---|
| Fast (<10s) | side_line, attn_magazine, chain_dlk | 5-10s |
| Medium (10-20s) | bandcamp, the_quietus, post_punk_com | 15-20s |
| Slow (20-30s) | sequenza21, froots, five_against_four | 25-30s (some timeout) |
