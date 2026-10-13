# Songlines Paywall Investigation (2026-06-14)

## Problem
`scrape_songlines.py` returns data but all Songlines reviews score 1/10. LLM sees "Register now to continue reading" instead of actual review text.

## Root Cause
- **List page** (`/reviews`): Works without login — shows album, artist, rating, excerpt (~150 chars)
- **Detail page** (`/review/xxx`): Requires registration. curl returns paywall page, browser shows full content for first 2 views then paywall

## Free Account Limit
- **2 free articles/month** — confirmed by testing 4 reviews: first 2 showed full content, next 2 showed paywall
- Registration is free (email + password + name) but 2/month is useless for scraper (needs 10-20 per run)

## Technical Details
- Paywall is **JS-rendered**: curl gets "Register now to continue reading", browser gets full content
- The `scrape_songlines.py` calls `fetch_article_body(url)` which uses curl → gets paywall text
- LLM scoring then sees registration text instead of review → all score 1/10

## Solution
**Use listing page data only** — already sufficient for LLM scoring:
- Album name + artist
- Rating (★ count)
- Excerpt (~150 chars from listing)
- Label + issue date

**Modification:** Remove `fetch_article_body()` call from `scrape_songlines.py`, use listing excerpt as body.

## What Doesn't Work
- Free registration: only 2/month
- Multiple free accounts: impractical
- Browser-based scraping: still hits 2/month limit after first views
- Paid subscription: would work but costs £7.50/month

## Related
- `scrape_songlines.py` at `/home/liyifan/music-record/bin/scrape_songlines.py`
- `scrape_songlines.py` (root) at `/home/liyifan/scrape_songlines.py` — uses Camoufox API, also gets paywall
