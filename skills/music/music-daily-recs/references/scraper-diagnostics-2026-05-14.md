# 42-Site Scraper Diagnostics — 2026-05-14

Full investigation results after checking all 42 active scraper sites.

## Summary

| Category | Count | Detail |
|----------|-------|--------|
| ✅ Normal (3+ entries w/ excerpt) | 9 | bandcamp_daily, free_jazz_blog, hhv_mag, igloo_magazine, jazz_journal, jazz_trail, musique_machine, roots_world, the_quietus |
| 🟢 Fixed this session | 7 | +24 ProgArchives, +4 RhythmPassport, +3 ICIYL, +2 JazzTimes (RSS manual); +11 AAJ (baseline fix); +1 The Wire (feature format); Songlines + DownBeat URL fix (next cron) |
| 🟡 RSS exists but >3 days old | 6 | attn_magazine (Mar), five_against_four (May 9), modern_classical_music (May 2), new_music_buff (Apr 27), sequenza21 (May 6), chain_dlk (May 11) |
| 🔵 Playwright accessible but agent empty | 7 | the_rest_is_noise_ph, wild_city, hear65, point_of_departure, van_magazine, prog_mistress, progressor |
| 🔴 Cloudflare blocked | 2 | resident_advisor (details pages), all_about_jazz (individual review pages) |
| 🟢 Resolved post-audit | 1 | Boomkat — was ASN-skip, Camoufox fingerprint 2026-05-19 bypasses CF |
| 🟡 URL needs finding | 4 | bandwagon_asia, sea_of_tranquility, strangely_isolated_place, mixmag_asia |
| 💀 Dead/Stale | 1 | froots (RSS from 2021) |

## Per-Site Details

### 🟢 Fixed

| Site | Problem | Fix |
|------|---------|-----|
| progarchives | RSS URL fixed earlier but scraper didn't run | Manual RSS scrape: **+24 entries** (Deep Purple, Ian Anderson, etc.) |
| rhythm_passport | RSS working, agent returned empty | Manual RSS scrape: **+4 entries** (world music) |
| icareifyoulisten | RSS working (3 recent), agent empty | Manual RSS scrape: **+3 entries** |
| jazztimes | RSS working (2 recent), agent empty | Manual RSS scrape: **+2 entries** |
| all_about_jazz | 11 entries w/ empty excerpt, no site baseline | SITE_TAGS + pen logic (tm>=3 no penalty): **+11 passing >=6** |
| the_wire | Feature format not recognized | `type: feature` support added; RSS has 91 items w/ full text in CDATA |
| songlines | `reviews_url` set to `/category/reviews` (500 error) | Changed to `/reviews-hub` (valid) |
| downbeat | `reviews_url` set to homepage `/` | Changed to `/reviews` (valid, 157 pages of reviews) |

### 🟡 RSS exists but items older than 3 days

| Site | RSS Items | Latest | Problem |
|------|-----------|--------|---------|
| attn_magazine | 15 | 2026-03 | Last post 2+ months ago. Site may be dormant |
| five_against_four | 10 | 2026-05-09 | Estonian Music Days festival coverage, not daily |
| modern_classical_music | 10 | 2026-05-02 | Monthly-ish posting |
| new_music_buff | 10 | 2026-04-27 | Monthly-ish posting |
| sequenza21 | 10 | 2026-05-06 | Weekly-ish posting |
| chain_dlk | 1 | 2026-05-11 | Very infrequent (1 item in the entire RSS) |

These sites consistently return empty because they post slower than the 3-day window. Consider widening to 7 days for low-frequency sites.

### 🔵 Playwright accessible but returned empty

These sites load via browser_navigate (HTTP 200) but the scraper agent returned `[]`. Likely causes:
- Agent timeout during Playwright navigation
- Cookie consent banners blocking content extraction
- JavaScript rendering issues with Camoufox

| Site | HTTP | Notes |
|------|------|-------|
| therestisnoiseph.com | 200 | Music Reviews page exists |
| thewildcity.com | 200 | Asian experimental/electronic |
| hear65.bandwagon.asia | 200 | Singapore music site |
| pointofdeparture.org | 200 | Creative music journal |
| van-magazine.com | 200 | Classical criticism |
| progmistress.com | 200 | Progressive rock reviews |
| progressor.net | 200 | Progressive rock reviews |

### 🔴 Cloudflare blocked

| Site | Blocked | What works |
|------|---------|-----------|
| resident_advisor (ra.co) | Individual review pages 403 | `/reviews` list page works (but details blocked) |
| all_about_jazz | Individual review pages 403 | `/reviews` list page works (metadata only) |

### 🟡 URL investigation needed

| Site | Current URL | Tried (all 404) |
|------|------------|------------------|
| bandwagon.asia | `/` | `/reviews`, `/music`, `/articles`, `/news` — homepage has Reviews section in footer, URL unknown |
| seaoftranquility.org | `/category/reviews` | `/reviews`, `/` works as homepage |
| astrangelyisolatedplace.com | `/` | `/reviews`, `/articles`, `/music` — all 404, site may have redesigned |
| mixmag.asia | `/category/reviews` | `/reviews` — all 404 |

### 💀 Dead/stale

| Site | RSS Latest | Status |
|------|-----------|--------|
| frootsmag.com | February 2021 | RSS shows "Podwireless – March 2021" as newest. Site appears to have stopped publishing. Consider `crawl_strategy: skip`. |
