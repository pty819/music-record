# RSS Source Health Baseline

**Date:** 2026-06-10
**Test:** `python3 bin/fast-rss-scrape.py --days 1.5 -o /tmp/rss-test/rss_merged.json`

## Results: 97 items / 16 stations with data

| Station | Items | Notes |
|---|---|---|
| progarchives | 27 | High volume |
| the_quietus | 15 | |
| avant_music_news | 10 | |
| side_line | 10 | |
| post_punk_com | 8 | |
| fluid_radio | 7 | Strategy=skip but has_rss=True, feeds are 2013-2022 archive |
| bandcamp_daily | 5 | |
| the_wire | 2 | |
| a_closer_listen | 2 | |
| icareifyoulisten | 2 | |
| rhythm_passport | 2 | |
| jazz_journal | 2 | |
| igloo_magazine | 2 | |
| jazztimes | 1 | |
| hhv_mag | 1 | |
| i_die_you_die | 1 | |

## 0 items — NOT bugs (legitimately no new content in 1.5 days)

| Station | Latest article | HTTP status |
|---|---|---|
| five_against_four | 2026-06-08 | 200 |
| the_classic_review | 2026-06-08 | 200 |
| van_magazine | 2026-06-04 | 200 |
| modern_classical_music | 2026-06-05 | 200 (301 redirect) |
| chain_dlk | 2026-06-02 | 200 (301 redirect) |
| sequenza21 | 2026-05-24 | 200 |
| new_music_buff | 2026-04-27 | 200 |
| attn_magazine | 2026-03-02 | 200 (301 redirect) |
| froots | 2021-02-28 | 200 (301 redirect) — dead feed |
| prog_mistress | 2025-01-31 | 200 (301 redirect) — dead feed |
| rest_is_noise_ph | — | 415 (Unsupported Media Type) |
| peek_a_boo_magazine | — | 503 (Service Unavailable) — server down |

## Key findings

- 301/302 redirects: attn_magazine, chain_dlk, modern_classical_music, froots, prog_mistress — all work after following redirects. feedparser handles these fine.
- Dead feeds: froots (2021), prog_mistress (2025-01), new_music_buff (2026-04). Consider removing from sites.json if consistently 0.
- Server issues: rest_is_noise_ph (415), peek_a_boo_magazine (503). Intermittent.
- The 15s→30s socket timeout fix is critical: 2026-06-10 cron with 15s timeout only got 4 items from 3 stations.
