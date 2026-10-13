# 2026-06-10: Cron Used Stale v7.0 Skill

## What happened

At 04:28 cron `ec5ea562d589` fired. Step 1 `git pull` fetched the then-latest code (v7.0).
Later that morning, two commits landed:
- `a8902a8` — RSS timeout 15→30s, HTML_SCRIPT_IDS 12→18
- `2bb6833` — boomkat + point_of_departure moved back to Camoufox (they use REST API)

The cron session had already completed Step 1 by then, so it ran the entire pipeline with v7.0 logic.

## Impact

| Layer | v7.0 (what ran) | v7.2 (expected) |
|-------|-----------------|-----------------|
| RSS socket timeout | 15s → 4 items / 3 stations | 30s → 27+ items |
| HTML scripts | 12 (missing 6) | 18 |
| Camoufox workers | 9 (6 unnecessary) | 3 |
| Final report | 82 items / 8 sources (Camoufox saved it) | Would have ~50+ from RSS+HTML alone |

The Camoufox workers compensated — boomkat alone contributed 49 items. The report was
correctly generated and pushed (81 recommendations in `recommend/2026-06-10.md`).

## Detection method

Checked cron output file header:
```
grep -m1 "version:" ~/.hermes/cron/output/ec5ea562d589/2026-06-10_04-28-11.md
# → version: 7.0 (expected 7.2)
```

## Lessons

1. **Step 1 `git pull` is a one-shot** — it runs at cron start and never again. Code committed after cron starts won't be picked up until the next day.
2. **Always verify the next cron run's version** after committing pipeline changes.
3. **Consider `hermes cron run` for immediate validation** of critical fixes instead of waiting for the next scheduled run.
