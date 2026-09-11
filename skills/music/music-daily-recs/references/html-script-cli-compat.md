# HTML Script CLI Compatibility & Output Requirements

**Date:** 2026-06-10
**Context:** `scrape_html_parallel.py` passes `--days 1.5` to all scripts via subprocess. Three categories of issues discovered and fixed.

## Issue 1: CLI `--days` Incompatibility (rc=2)

| Script | Original CLI | Fix Applied |
|---|---|---|
| `scrape_hear65.py` | `--hours HOURS` | Added `--days` → `hours = args.days * 24` |
| `scrape_roots_world.py` | `--ref-date REF_DATE` | Added `--days` → passed to `scrape(days=)` |
| `scrape_world_music_central.py` | `--hours HOURS` | Added `--days` → overrides `--hours` |

**Pattern for new scrapers** — always add `--days` support:
```python
parser.add_argument("--days", type=float, default=None,
                    help="Cutoff in days (overrides --hours if set)")
hours = args.days * 24 if args.days is not None else args.hours
```

## Issue 2: stdout Mode Scripts Not Printing to stdout (0-byte capture)

Scripts that only wrote to files (`json.dump(result, f)`) produced empty captures.

| Script | Problem | Fix |
|---|---|---|
| `truth_and_lies_music` | `json.dump` to hardcoded file path only | Added `print(json.dumps(result))` |
| `world_music_central` | `json.dump` to file only | Added `print(json.dumps(out))` |

**Rule**: stdout mode scrapers MUST `print(json.dumps(result))`. File write is optional backup.

**Verification**:
```bash
python3 scrape_X.py --days 1.5 > /tmp/test.json 2>/dev/null
python3 -c "import json; d=json.load(open('/tmp/test.json')); print(f'OK: {d[\"meta\"][\"total\"]} items')"
```

## Issue 3: pub_date=None Sort Crash

Some items have `"pub_date": null` or `""`. `list.sort()` crashes on `None < str`.

```python
# BAD
all_items.sort(key=lambda r: r.get("pub_date", ""), reverse=True)
# GOOD — None → ""
all_items.sort(key=lambda r: r.get("pub_date") or "", reverse=True)
```

## Issue 4: Camoufox Dependencies in HTML Group

Scripts calling `CAMOFOX_BASE` (`http://127.0.0.1:9377`) belong in Camoufox group, not HTML.

**Check**: `grep -l "CAMOFOX_BASE\|9377" bin/scrape_*.py`

Fixed: `wild_city` moved from HTML_SCRIPT_IDS to Camoufox (4 workers: boomkat, PoD, progressor, wild_city).

## Architecture (v7.3, 2026-06-10)

`scrape_html_parallel.py` uses `concurrent.futures.ThreadPoolExecutor`:
- Each scraper runs as subprocess, stdout captured via `subprocess.run(capture_output=True)`
- JSON parsed in memory, all items merged into single `html_reviews.json`
- `sea_of_tranquility` special-cased (out_dir mode — reads file after completion)
- No intermediate per-site files

## Verification Script

```bash
# Check all 17 scripts accept --days and output valid JSON
for s in scrape_all_about_jazz scrape_bandwagon_asia scrape_dark_entries scrape_downbeat \
         scrape_free_jazz_blog scrape_hear65 scrape_jazz_trail scrape_mixmag_asia \
         scrape_musique_machine scrape_resident_advisor scrape_roots_world \
         scrape_sea_of_tranquility scrape_songlines scrape_squids_ear \
         scrape_strangely_isolated_place scrape_truth_and_lies_music scrape_world_music_central; do
  python3 bin/${s}.py --help 2>&1 | grep -q "\-\-days" && echo "✅ $s --days" || echo "❌ $s --days"
done
```
