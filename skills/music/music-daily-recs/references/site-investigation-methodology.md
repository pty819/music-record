# Site Investigation Methodology

When a site returns empty scraper results, systematically investigate (in order):

## Phase 1: Quick triage

### 1. Check JSON output
```bash
cat ~/music-record/2026/05/2026-05-14/{site_id}_reviews.json
```
- Empty `[]` → scraper ran but found nothing
- Non-empty but `"excerpt": ""` → scraper found entries but couldn't get text

### 2. Check sites.json config
Look up the site in `/home/liyifan/.minimax/music-sites/sites.json`:
- `reviews_url` — where the scraper looks
- `has_rss` — RSS URL if configured
- `crawl_strategy` — playwright_headless / http_get / skip

### 3. Test RSS first (fastest)
```bash
curl -sL --max-time 10 "https://site.com/feed/" | head -5
# Expect: <?xml / <rss / <feed → valid
# Expect: DOCTYPE / 403 / 404 → invalid
```

If RSS valid, check dates:
```bash
python3 -c "
import feedparser
feed = feedparser.parse('https://site.com/feed/')
for e in feed.entries[:5]:
    pub = e.get('published','?')
    title = e.get('title','')[:60]
    print(f'{pub} | {title}')
"
```

### 4. Test HTTP status of reviews_url
```bash
curl -sL -o /dev/null -w "%{http_code}" --max-time 8 "https://site.com/reviews"
```

| Status | Meaning |
|--------|---------|
| 200 | Site accessible |
| 403 | Cloudflare / bot block |
| 404 | Wrong URL |
| 500 | Server error (broken path) |
| timeout | Site slow or down |

## Phase 2: Browse investigation (for Playwright sites)

Use `browser_navigate` to visit the `reviews_url` and check:

1. **Wrong URL?** Navigate the site's navigation to find the correct reviews section
2. **Paywalled?** Check if individual review pages need login/subscription
3. **No dates?** Check if list page shows publication dates (needed for 3-day filter)
4. **Click-through needed?** Some sites list only titles on the list page; actual content is on individual pages

## Phase 3: Find correct URL (when current URL is wrong)

Try common paths:
```
/reviews
/category/reviews
/reviews-hub
/music
/album-reviews
/editorial
/features
```

Check site navigation via browser_snapshot — look for links named "Reviews", "Album Reviews", "Music", "Articles".

## Phase 4: Classify the finding

| Cause | Action |
|-------|--------|
| Wrong URL | Update `reviews_url` in sites.json |
| Broken RSS URL | Fix `rss_url` or switch to `has_rss: false` + playwright |
| No recent content (3+ day window) | Accept as-is, or publish wider window for low-frequency sites |
| Cloudflare 403 | Add to Cloudflare list; accept metadata-only |
| Site dead/moved | Mark `crawl_strategy: skip` |
| Agent execution bug | Debug scraper body template or agent environment |
| Feature format (not album review) | Add `type: feature` handling to scraper body |

## 2026-05-14 Full Audit Results

See `references/scraper-diagnostics-2026-05-14.md` for the complete 42-site investigation results.
