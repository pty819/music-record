# HTML_SCRIPT_IDS Migration Log

## 2026-06-10: 12 → 20 (9 sites migrated from Camoufox)

### Problem
9 sites had working `scrape_*.py` HTTP scripts in `bin/` but were NOT registered in `HTML_SCRIPT_IDS`. They fell through to `get_sites()` and got assigned to Camoufox browser workers — slower, less reliable, and unnecessary.

### Migration
Added to `HTML_SCRIPT_IDS` in `kanban-swarm.py` and `SCRIPTS` in `scrape_html_parallel.py`:

| Site ID | Script | Previous route |
|---|---|---|
| bandwagon_asia | scrape_bandwagon_asia.py | Camoufox |
| boomkat | scrape_boomkat.py | Camoufox |
| hear65 | scrape_hear65.py | Camoufox |
| point_of_departure | scrape_point_of_departure.py | Camoufox |
| roots_world | scrape_roots_world.py | Camoufox |
| strangely_isolated_place | scrape_strangely_isolated_place.py | Camoufox |
| truth_and_lies_music | scrape_truth_and_lies_music.py | Camoufox |
| world_music_central | scrape_world_music_central.py | Camoufox |

### Naming quirk
`dark_entries_be` is the site_id in HTML_SCRIPT_IDS, but the script is `scrape_dark_entries.py` (no `_be` suffix). The `SCRIPTS` tuple in `scrape_html_parallel.py` maps this correctly: `("scrape_dark_entries", "dark_entries_be", "stdout")`.

### Result (initial)
- 20 HTML sites, 1 Camoufox (progressor — no scrape script exists)
- `--max-parallel` default changed from 12 to 20

### Result (corrected 2026-06-10 evening)
- boomkat and point_of_departure **wrongly** moved to HTML — their scripts call Camoufox REST API (`CAMOFOX_BASE`), not pure HTTP. Moved back to Camoufox.
- wild_city also depends on Camoufox REST API but still in HTML_SCRIPT_IDS (deferred fix).
- hear65, roots_world, world_music_central didn't accept `--days` arg → fixed with `--days` support.
- **Final: 18 HTML (incl. wild_city⚠️) + 3 Camoufox (boomkat, point_of_departure, progressor) + 3 skip**

### CLI `--days` argument mismatch (discovered & fixed 2026-06-10)
`scrape_html_parallel.py` passes `--days 1.5` to ALL scrapers. Three scripts didn't accept it:

| Script | Accepted args | Fix applied |
|---|---|---|
| `scrape_hear65.py` | `--hours` | Added `--days` (overrides `--hours` via `args.days * 24`) |
| `scrape_roots_world.py` | `--ref-date`, `--max-pages` | Added `--days` (passed to `scrape(days=)`, used in `timedelta(days=)`) |
| `scrape_world_music_central.py` | `--hours`, `--date` | Added `--days` (overrides `--hours` in cutoff calc) |

**Lesson**: New scrapers MUST be tested with `python3 bin/scrape_<site>.py --days 1.5` before adding to `scrape_html_parallel.py`. See pitfall "scrape 脚本不认 `--days` 参数" in SKILL.md and `references/html-script-cli-compat.md` for fix patterns.
### How to add a new HTML site
1. Write `bin/scrape_<site_id>.py` (must accept `--days N` and output JSON to stdout)
2. **Verify CLI**: `python3 bin/scrape_<site_id>.py --days 1.5` — must not error
3. **Verify NOT Camoufox**: `grep -i CAMOFOX_BASE bin/scrape_<site_id>.py` — must return empty
4. Add to `HTML_SCRIPT_IDS` in `bin/kanban-swarm.py`
5. Add `("scrape_<site_id>", "<site_id>", "stdout")` to `SCRIPTS` in `bin/scrape_html_parallel.py`
6. Sync: `cp bin/scrape_<site_id>.py ~/.local/bin/ && cp bin/scrape_<site_id>.py ~/.hermes/skills/music/music-daily-recs/scripts/`

## 2026-09-11: progressor Camoufox → HTML

ProgressoR 已有 `bin/scrape_progressor.py`（纯 HTTP，`CAMOFOX_BASE` 为空）。站点 TLS 1.0 + 自签证书，Camoufox/Firefox 150+ 连不上。实测：

- `--days 1.5`：exit 0，197 候选，0 条在 36h 窗口（月刊，最新 `Progtector: August 2026`）
- `--days 100`：78 条完整乐评，`fetch_errors=0`

迁入 HTML 层，避免再派 LLM worker：

1. `scrape_html_parallel.py:SCRIPTS` 加 `("scrape_progressor", "progressor", "out_dir")`（脚本写文件不 print stdout）
2. `kanban-swarm.py:HTML_SCRIPT_IDS` 加 `progressor`
3. `data/sites.json` `crawl_strategy`: `playwright_headless` → `html_scrape`
4. `python3 bin/gen_skill_site_table.py --write`

**Result: 17 HTML + 5 Camoufox (boomkat, point_of_departure, wild_city, jazztokyo, musicircus) + 2 skip**

## 2026-09-11: boomkat Camoufox worker → HTML 脚本层

`bin/scrape_boomkat.py` 已是确定性进程：Camoufox REST + `--days` + stdout JSON + CF 15s 早退。实测 2026-09-11：`CF check: Just a moment...|0` → `cf_blocked=true`、exit 0、空 JSON。迁入 HTML 层后不再派 LLM worker（CF 后反复开 tab 烧 iteration 的旧故障面消失）。

1. `scrape_html_parallel.py:SCRIPTS` 加 `("scrape_boomkat", "boomkat", "stdout")`
2. `kanban-swarm.py:HTML_SCRIPT_IDS` 加 `boomkat`
3. `data/sites.json` `crawl_strategy`: `playwright_headless` → `html_scrape`
4. `python3 bin/gen_skill_site_table.py --write`

**Result: 18 HTML + 4 Camoufox (point_of_departure, wild_city, jazztokyo, musicircus) + 2 skip**

## 2026-09-11: boomkat 撤回 HTML，回到 Camoufox worker

用户要求 Boomkat 继续走 LLM worker 自主探索，不进确定性 HTML 脚本层。已撤销上一节改动：

1. 从 `SCRIPTS` / `HTML_SCRIPT_IDS` 移除 `boomkat`
2. `data/sites.json` `crawl_strategy` 恢复 `playwright_headless`
3. `python3 bin/gen_skill_site_table.py --write`

脚本 `scrape_boomkat.py` 仍保留在 `bin/`，但不由 `scrape_html_parallel.py` 调用。Kanban worker body 仍含 `BOOMKAT_EARLY_EXIT`（CF 后禁止反复开 tab）。

**Result: 17 HTML + 5 Camoufox (boomkat, point_of_departure, wild_city, jazztokyo, musicircus) + 2 skip**
