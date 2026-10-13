# RSS Verification Best Practices

**Rule: Never guess RSS feed URLs. Always curl-verify before committing.**

## Why

RSS feeds are fragile — common issues:
- Feed location guessed from domain + `/feed/` returns 404
- Feed returns 403 (server blocks unknown user-agents)
- Feed exists but returns HTML not XML (server fallback)
- Feed returns empty (no recent content)

Any of these means `has_rss: false` + `crawl_strategy: playwright_headless`.

## Verification Process

```bash
# 1. Guess feed URL (common patterns)
curl -sL --max-time 10 "https://site.com/feed/" | head -5
# → XML starting with <?xml or <rss/<feed → valid RSS

curl -sL "https://site.com/rss" | head -5
curl -sL "https://site.com/category/reviews/feed/" | head -5

# 2. Check for HTML/404/403 response
# If you see DOCTYPE, 403 Forbidden, 404 — NOT valid RSS

# 3. If RSS is invalid → configure as playwright_headless:
#   "has_rss": false,
#   "crawl_strategy": "playwright_headless",
#   "rss_url": null

# 4. If RSS is valid → test content extraction
python3 -c "
import feedparser, sys
feed = feedparser.parse(sys.stdin.buffer.read())
entries = feed.entries
print(f'Entries: {len(entries)}')
for e in entries[:3]:
    print(f'  {e.get(\"title\",\"?\")} — {e.get(\"link\",\"?\")}')
" <<< "$(curl -sL 'https://site.com/feed/')"
```

## Common Patterns for Music Review Sites

| Site | Working RSS Pattern |
|------|-------------------|
| The Wire | `https://www.thewire.co.uk/home/rss` |
| Avant Music News | `https://avantmusicnews.com/feed/` |
| A Closer Listen | `https://acloserlisten.com/feed/` |
| Louder Than War | ❌ `album-reviews/feed/` → 403, use playwright |
| Sleeping Village Reviews | ❌ `/feed/` → 404, use playwright |

## Darkwave / Industrial Site RSS Patterns

| Site | Working RSS Pattern |
|------|-------------------|
| Side-Line | `https://www.side-line.com/feed/` |
| Post-Punk.com | `https://www.post-punk.com/feed/` |
| I Die: You Die | `https://www.idieyoudie.com/feed/` |
| Peek-A-Boo Magazine | `http://www.peek-a-boo-magazine.be/all.rss` |
| Dark Entries (BE) | No RSS → Camoufox instead |

## Camoufox Verification (for sites without RSS)

When a site has no working RSS, test browser accessibility before adding:

```bash
# 1. HTTP check
curl -sL -o /dev/null -w "%{http_code}" --max-time 8 "https://site.com"

# 2. SSL health check
curl -v --max-time 5 "https://site.com" 2>&1 | grep "SSL"

# 3. Camoufox (browser_navigate) — expect:
#   200 + valid review list → add as playwright_headless
#   500 error / SSL fail → site dead, skip
```

Dead domain checklist: `curl -v` shows `SSL_ERROR_SYSCALL` at TLS handshake → certificate broken, site effectively dead. Camoufox returning 500 confirms it.

## When to Use Playwright Instead

If RSS fails for any reason (403/404/HTML-not-XML), **do NOT mark as skip**. Use `playwright_headless` — the site is still valuable, RSS was just unavailable.

## Commit Checklist

Before pushing a new site to GitHub:
- [ ] RSS verified with `curl` + `feedparser`
- [ ] If RSS valid: `has_rss: true`, `rss_url` set correctly
- [ ] If RSS invalid: `has_rss: false`, `crawl_strategy: playwright_headless`, `rss_url: null`
- [ ] JSON format validated (`python3 -m json.tool`)
