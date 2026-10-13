# HTML Script CLI Audit (2026-06-10)

All 17 HTML scripts were audited for compatibility with `scrape_html_parallel.py --days 1.5`.

## CLI Compatibility Matrix

| Script | `--days` | stdout JSON | Notes |
|---|---|---|---|
| scrape_all_about_jazz.py | ✅ | ✅ | Cloudflare, may return 0 items |
| scrape_bandwagon_asia.py | ✅ | ✅ | urllib direct |
| scrape_dark_entries.py | ✅ | ✅ | |
| scrape_downbeat.py | ✅ | ✅ | |
| scrape_free_jazz_blog.py | ✅ | ✅ | |
| scrape_hear65.py | ✅ (added) | ✅ | Was `--hours` only, added `--days` override |
| scrape_jazz_trail.py | ✅ | ✅ | --max-pages 3 |
| scrape_mixmag_asia.py | ✅ | ✅ | Camoufox for body fetch |
| scrape_musique_machine.py | ✅ | ✅ | |
| scrape_resident_advisor.py | ✅ | ✅ | Cloudflare |
| scrape_roots_world.py | ✅ (added) | ✅ | Was `--ref-date` only, added `--days` |
| scrape_sea_of_tranquility.py | ✅ | ❌ (out_dir) | Uses `--out-dir` mode, writes own file |
| scrape_songlines.py | ✅ | ✅ | 180s timeout needed |
| scrape_squids_ear.py | ✅ | ✅ | 100+ items per run |
| scrape_strangely_isolated_place.py | ✅ | ✅ | urllib, may return 0 items |
| scrape_truth_and_lies_music.py | ✅ | ✅ (added) | Was file-write only, added `print(json)` |
| scrape_world_music_central.py | ✅ (added) | ✅ (added) | Was `--hours` only + file-write, added both |

## Camoufox-Dependent Scripts (NOT in HTML group)

| Script | Dependency | Group |
|---|---|---|
| scrape_wild_city.py | `CAMOFOX_BASE = http://127.0.0.1:9377` | Camoufox worker |
| scrape_boomkat.py | `CAMOFOX_BASE` | Camoufox worker |
| scrape_point_of_departure.py | `CAMOFOX_BASE` | Camoufox worker |

## How to Add a New Script

1. `--help` must show `--days` parameter
2. `python3 scrape_X.py --days 1.5 2>/dev/null > /tmp/t.json && stat -c%s /tmp/t.json` — must be > 0
3. `grep -i camoufox scrape_X.py` — must NOT depend on Camoufox REST API
4. Add to `SCRIPTS` list in `scrape_html_parallel.py` and `HTML_SCRIPT_IDS` in `kanban-swarm.py`
