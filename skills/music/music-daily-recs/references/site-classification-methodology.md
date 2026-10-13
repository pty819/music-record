# How to Classify a New Site (RSS / HTML / Camoufox)

## Decision Tree
1. **RSS**: `has_rss=True AND rss_url` non-empty → `fast-rss-scrape.py`
2. **HTML**: Has `scrape_<id>.py` in bin/ AND script uses pure HTTP (urllib/curl/feedparser/requests) OR calls a public REST/GraphQL API
3. **Camoufox**: Script calls `CAMOFOX_BASE` REST API, OR has `crawl_strategy=playwright_headless` with no script
4. **Skip**: `crawl_strategy=skip` (but check if `has_rss` overrides)

## How to Verify Script Type
```bash
# Check imports — pure HTTP?
grep -E "^import |^from " bin/scrape_<site>.py | grep -iE "urllib|requests|feedparser|curl|http"

# Check for Camoufox dependency
grep -n "camoufox\|Camoufox\|CAMOFOX_BASE\|playwright" bin/scrape_<site>.py

# Check subprocess calls — are they curl or camoufox?
grep -n "subprocess" bin/scrape_<site>.py
```

## SPA Detection (Next.js / React)

If a site returns 0 items from HTML parsing, check if it's a SPA:

```bash
# Check for Next.js
curl -sL 'https://site.com/reviews' -H 'User-Agent: Mozilla/5.0' | grep -c '__NEXT_DATA__'

# Check for Apollo/React
curl -sL 'https://site.com/reviews' -H 'User-Agent: Mozilla/5.0' | grep -c '__APOLLO_STATE__'
```

If found, HTML parsing will return 0 elements. Options:
1. **GraphQL API**: Many SPAs have a public GraphQL endpoint. Test: `curl site.com/graphql -d '{"query":"{ __typename }"}'`
2. **`__NEXT_DATA__` JSON**: Extract data from the `<script id="__NEXT_DATA__">` tag
3. **REST API**: Check network requests in browser DevTools
4. **Camoufox**: Last resort — load the page in a real browser

**Case study**: `resident_advisor` (ra.co) is a Next.js SPA. The reviews page has no `<div class="review">` elements in server HTML. Fixed by using `ra.co/graphql` → `reviews(type: ALL)` query which returns structured JSON with full article content.

## Systematic API/GraphQL Investigation for HTML Sites

When an HTML site returns 0 items or you want to find a faster path, run this checklist:

```bash
# 1. Check for Next.js (__NEXT_DATA__ in page source)
curl -sL 'https://site.com/' -H 'User-Agent: Mozilla/5.0' | grep -c '__NEXT_DATA__'

# 2. Check for GraphQL endpoint
curl -sL 'https://site.com/graphql' -d '{"query":"{ __typename }"}' -H 'Content-Type: application/json'

# 3. Check for WordPress REST API
curl -sL 'https://site.com/wp-json/wp/v2/posts?per_page=1' | head -c 200

# 4. Check for RSS feed
curl -sL 'https://site.com/feed/' -o /dev/null -w "%{http_code}"
```

If any of these return data, prefer the API over HTML parsing. Faster, more reliable, structured output.

**Case study: worldmusiccentral** — had `has_rss=False` in sites.json despite having a live RSS feed at `/feed/`. Investigation found 5 recent entries including album reviews. Migrated from HTML scraper to RSS: changed `has_rss=True`, `crawl_strategy=http_get`, removed from `HTML_SCRIPT_IDS`. Result: 5 entries in ~2s vs 10s+ HTML scraping.

**2026-06-10 full audit**: Checked all 17 HTML sites for API opportunities. Result: only Resident Advisor (GraphQL) and worldmusiccentral (RSS) had alternatives. The other 15 are traditional WordPress/static sites with no modern frameworks.

## Gotchas
- **Docstring lies**: `scrape_boomkat.py` docstring says "Camoufox-based" but some scripts use urllib for API calls TO the Camoufox REST server. The docstring is correct — it needs Camoufox.
- **Dual mode**: `scrape_strangely_isolated_place.py` tries urllib first, falls back to Camoufox. Classify as HTML (urllib succeeds most of the time).
- **mixmag_asia**: `crawl_strategy=skip` in sites.json BUT still in HTML_SCRIPT_IDS. `scrape_html_parallel.py` runs it via its own SCRIPTS list (independent of sites.json). The kanban `get_sites()` skips it, but the cron Step 3 script still runs it.
- **fluid_radio**: `crawl_strategy=skip` BUT `has_rss=True` → RSS priority wins. Feed is 2013-2022 historical, may occasionally return items.
- **wild_city**: Script calls `CAMOFOX_BASE` REST API — must be in Camoufox group, NOT HTML. Moved 2026-06-10.
- **resident_advisor**: Next.js SPA — HTML has no review elements (React renders client-side). Fixed 2026-06-10: rewrote to use `ra.co/graphql` API. When debugging a 0-item site, check for `__NEXT_DATA__` in the page source — if present, the site is a SPA and HTML parsing won't work.
- **squids_ear**: 2026-08-15 恢复（amer1 IP 可直连，hysteria-Amsterdam 仍 403）。见 SKILL.md 2026-08-16 更新。
- **world_music_central**: Was in HTML_SCRIPT_IDS despite having a live RSS feed. `sites.json` had `rss_url` set but `has_rss=False`. Fixed 2026-06-10: migrated to RSS. Now 29 RSS, 16 HTML.

## Current Distribution (v7.4, 2026-06-10)
- 29 RSS (28 + world_music_central)
- 16 HTML (pure HTTP scrapers, including RA via GraphQL)
- 4 Camoufox (boomkat, point_of_departure, progressor, wild_city)
- 2 skip (syrphe, textura)

## When Adding a New Site
1. Write `bin/scrape_<id>.py`
2. Determine: pure HTTP or needs Camoufox REST?
3. Add to `HTML_SCRIPT_IDS` in `kanban-swarm.py` (if HTTP)
4. Add to `SCRIPTS` in `scrape_html_parallel.py` (if HTTP)
5. Update SKILL.md site distribution table
6. **Verify CLI compatibility**: run `python3 bin/scrape_<id>.py --days 1.5` — script MUST accept `--days` (see below)
7. **Verify stdout output**: script MUST print JSON to stdout (not just write to file) — parallel scraper captures stdout
8. **Check for SPA**: if the site returns 0 items, run the SPA detection commands above before assuming the script is broken

## CLI Compatibility Requirement (Critical)

`scrape_html_parallel.py` passes `--days 1.5` to ALL scripts. Every HTML scrape script MUST accept this argument.

**Common mismatch patterns:**
| Script uses | Parallel passes | Fix |
|---|---|---|
| `--hours` only | `--days` | Add `--days` arg, convert: `hours = args.days * 24` |
| `--ref-date` only | `--days` | Add `--days` arg, pass to `scrape()` function |
| `--date` only | `--days` | Add `--days` arg, compute cutoff from it |

**Pitfall**: Scripts that only write to file (no stdout print) produce 0-byte output in parallel scraper. The parallel scraper redirects stdout to `{site_id}_reviews.json`. If script uses `json.dump(result, f)` to a file path instead of `print(json.dumps(result))`, the captured file will be empty.

**Verified fix pattern** (add after file write):
```python
print(json.dumps(result, indent=2, ensure_ascii=False))  # for parallel scraper
```

**Scripts fixed 2026-06-10:**
- `scrape_hear65.py` — added `--days` (converts to hours)
- `scrape_roots_world.py` — added `--days` (passes to `scrape()`)
- `scrape_world_music_central.py` — added `--days` + stdout print
- `scrape_truth_and_lies_music.py` — added stdout print (was file-only)
- `scrape_wild_city.py` — moved to Camoufox group (depends on REST API)
- `scrape_resident_advisor.py` — rewritten to use GraphQL API (was HTML parsing)

## Debugging 0-Item Sites

See `references/debugging-zero-item-scrapers.md` for the systematic methodology.
