# Scrape Script CLI Args Matrix

> Created 2026-06-08 after user caught SKILL.md Step 3 hardcoding `--days 1.5` for all scripts, but `scrape_songlines.py` doesn't support `--days`. Step 3 must auto-detect per-script args.
>
> **Last expanded 2026-06-08 (same day, later)** after user requested full `bin/scrape_*.py` (20 scripts) verification at 1.5-day window. Found 6 real bugs that need fixing or working around.

## How to use

Before running any `scrape_*.py`, run `--help` and check the supported args. Don't trust the SKILL.md template — re-verify on each cron run because scripts drift.

```bash
# Quick matrix
for f in /home/liyifan/music-record/bin/scrape_*.py; do
    name=$(basename "$f" .py)
    args=$(timeout 10 python3 "$f" --help 2>&1 | grep -oE "(--[a-z-]+)" | sort -u | tr '\n' ' ')
    echo "$name: $args"
done
```

⚠️ `scrape_sea_of_tranquility.py` / `_v2.py` 没 argparse——`--help` 会 hang（脚本内把 `--help` 当 URL 抓）。用 `timeout 10` 必加。

## Full matrix — 20 scripts (verified 2026-06-08 second pass)

| Script | `--days` | `--ref-date` | `--hours` | `--date` | `--max-pages` | Argparse | Notes / 真 bug |
|--------|:--------:|:------------:|:---------:|:--------:|:-------------:|:--------:|---------------|
| `scrape_all_about_jazz.py` | ✅ | ❌ | ❌ | ❌ | `--pages` | ✅ | L3 (CAMOFOX_BASE) |
| `scrape_bandwagon_asia.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L2 (urllib/bs4). 1.5 天窗口实测 1 条 ✅ |
| `scrape_boomkat.py` | ✅ | ❌ | ❌ | ❌ | `--pages --limit` | ✅ | L3 (CAMOFOX_BASE). 50 items 需 180s+ |
| `scrape_boomkat_bodies.py` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **pass-2 辅助脚本**——接 boomkat.py 产物抓全文，需传 `in_path out_path`，**不在 1.5 天验证范围** |
| `scrape_dark_entries.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L2 (urllib/bs4). 1.5 天窗口 0 条（站点低频，正常）|
| `scrape_downbeat.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L3 (CAMOFOX_BASE 兜底，urllib 主). 50s timeout |
| `scrape_free_jazz_blog.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L2 (urllib/bs4). 1.5 天窗口 2 条 ✅ |
| `scrape_hear65.py` | ✅ (2026-06-10) | ❌ | **✅** | ❌ | ❌ | ✅ | L2. **已修 2026-06-10**: added `--days` (overrides `--hours` via `args.days * 24`) |
| `scrape_jazz_trail.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L2 (urllib/bs4). **🔴 主循环 `while next_url:` 无早停**（2026-06-09 实测翻 86 页 = 252s 跑完，86 页里只有 1 页有 in-window item）。翻页 URL 是 `?offset=<ms_timestamp>` 按 post 时间倒序，j-t 自 2009 起累计数千篇 blog——理论需 200+ 页才到底。修法：加 "连续 1-2 页 `new_count==0` break"。详见 `references/scrape-jazz-trail-pagination-investigation.md` |
| `scrape_mixmag_asia.py` | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ | L3 (CAMOFOX_BASE). 1.5 天 8 条 ✅ |
| `scrape_musique_machine.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L3 (CAMOFOX_BASE). 1.5 天 0 条（正常）|
| `scrape_resident_advisor.py` | ✅ | ❌ | ❌ | `--cutoff` | ✅ | ✅ | L3 (CAMOFOX_BASE). 50s 不够 |
| **`scrape_roots_world.py`** | ✅ (2026-06-10) | **✅** | ❌ | ❌ | ✅ | ✅ | L2. **已修 2026-06-10**: added `--days` (passed to `scrape(days=)`, uses `timedelta(days=)` for cutoff). 日期过滤仍为 homepage-level（无 per-article date parsing）|
| `scrape_sea_of_tranquility.py` | ❌ | ❌ | ❌ | `--out-dir` | `--limit` | ✅ | L2 (urllib/bs4). **唯一支持 `--out-dir` 自写文件的脚本**（其余 11 个走 stdout）。`bin/scrape_html_parallel.py` 用 `mode=out_dir` 分流（2026-06-09 wrapper fix）。**`--help` 仍会 hang**（脚本内把 `--help` 当 URL 抓）——`get_args` 必须用 `timeout 10`。1.5 天窗口下 0-3 条（看时间点），早停 5 条连续 < cutoff 有效 |
| `scrape_sea_of_tranquility_v2.py` | ❌ | ❌ | ❌ | ❌ | ❌ | **❌** | **🐛 BUG: 同 v1**. `cutoff = now - timedelta(hours=36)` hardcoded ✅. 但无 argparse. 实测跑会撞 502（seaoftranquility.org 上游问题）|
| `scrape_songlines.py` | ❌ | **✅** | ❌ | ❌ | ✅ | ✅ | L2. **用 `--ref-date 2026-06-07` 不用 `--days`** |
| `scrape_squids_ear.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L2. 1.5 天 0 条（CF 拦截，正常）|
| **`scrape_truth_and_lies_music.py`** | ✅ | ❌ | ❌ | ❌ | `--pages` | ✅ | L3 (CAMOFOX_BASE). **🐛 BUG: 写死输出路径** — `output_path = ".../2026-06-06/..."` 永远写 6-06 目录，跟当天日期无关 |
| `scrape_wild_city.py` | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | L3 (CAMOFOX_BASE). 50s 不够 |
| `scrape_world_music_central.py` | ❌ | ❌ | **✅** | ✅ | ❌ | ✅ | 走 RSS. **用 `--hours 36` 不用 `--days 1.5`**. 1.5 天 2 条 ✅ |

**汇总（按参数分桶）**：
- **13 个**支持 `--days N`（占大多数）
- **3 个**只支持 `--hours N`（hear65, world_music_central, ...；实际 2 个）
- **3 个**只支持 `--ref-date YYYY-MM-DD`（roots_world, songlines, ...；实际 2 个）
- **2 个**完全无 argparse（sea_of_tranquility v1/v2）—— 裸跑
- **1 个**是 pass-2 辅助（boomkat_bodies）—— 不在 1.5 天窗口范围

## 6 个真 bug（2026-06-08 全量验证后）

按修复优先级：

### 🔴 P0: `scrape_truth_and_lines_music.py` 写死输出路径

```python
# 行 355:
output_path = "/home/liyifan/music-record/2026/06/2026-06-06/truth_and_lies_music_reviews.json"
```

**问题**：永远写 6-06 目录——`process_reviews.py` 找的是当天日期的目录，**这个站的产物永远找不到**。

**修法**：改用 `os.environ.get('HERMES_KANBAN_WORKSPACE', ...)` 或 argparse 接 `--out`。

### 🔴 P0: `scrape_roots_world.py` 不做日期过滤

```python
# meta 里:
"note": "RootsWorld has no published dates on articles; all home-page -26 articles included"
```

**问题**：1.5 天窗口下抓首页全部 27 条，包括几年前的——**违反 cron 36h 窗口硬约束**。

**修法**：要么解析每篇文章页找日期，要么把 ref-date 检查放进 article 抓取步骤。

### 🟡 P1: `scrape_sea_of_tranquility.py` `--help` hang（部分修：2026-06-09）

**问题（修前）**：
1. `python3 scrape_sea_of_tranquility.py --help` 会 hang（脚本内 urllib 把 `--help` 当 URL 抓）
2. v1 行 13: `cutoff = (now - timedelta(hours=36)).isoformat()` 硬编码 36h

**已修**（commit `8c2a36f`，`bin/scrape_html_parallel.py` 的 `mode=out_dir` 分流）：
- 脚本现已**支持** `--out-dir` 自写文件 + `--limit`（其余 11 个走 stdout）
- wrapper `get_args` 必须用 `timeout 10`（仍会 hang，但不阻塞 cron）
- 1.5 天窗口**不能**用 `--days` 改——保持 36h 硬编码；想用别的窗口需先改脚本

**剩余工作**：把 `cutoff = ...` 改成 argparse 接 `--hours 36`（保持 backward compat：不传参 = hardcoded 36h）。

## General pattern (2026-06-08 user preference)

- **1.5 天 / 36h** 是用户硬约束。**任何**手动验证都用 `--days 1.5` 或 `--hours 36`
- 加宽窗口 = 把 36h 抓不到的旧文当新数据 → 污染 cutover 日的报告
- 1.5 天窗口下 0 条 = "脚本正常 + 站点低频" 的合理结果，**直接接受**写空 JSON + note

**Step 3 模板禁止**用统一 `--days 1.5` 写死。正确做法：

```python
# 运行时先看每个脚本的 --help
def get_args(s):
    p = subprocess.run(['timeout', '10', 'python3', f'{SCRIPTS_DIR}/{s}.py', '--help'],
                       capture_output=True, text=True)
    help_txt = p.stdout + p.stderr
    if '--days' in help_txt:
        return ['--days', '1.5']
    if '--ref-date' in help_txt:
        return ['--ref-date', '$(date +%Y-%m-%d)']
    if '--hours' in help_txt:
        return ['--hours', '36']
    return []  # 裸跑（sea_of_tranquility v1/v2 用 hardcoded 36h）
```

⚠️ `get_args` 必须用 `timeout 10`——sea_of_tranquility v1/v2 没 argparse 会 hang。

## When a script's CLI changes

The matrix above is a snapshot. Before any cron / manual run:

```bash
timeout 10 python3 bin/SCRIPT_NAME.py --help
```

If args changed, update this file. This is **not** a static doc — it's a maintenance checklist.

## Related pitfalls

- §4 #9 in SKILL.md — the constraint that forbids hardcoded `--days 1.5`
- §4 #7 — 1.5 day / 36h window discipline (never widen)
- §4 #8 — work-flow traps (maintainer overanalysis)
- `references/site-investigation-methodology.md` — how to investigate when a site returns 0
- `references/2026-06-08-scrape-script-full-verification.md` — full 20-script verification transcript
