---
name: music-daily-recs
description: 每日巡检 48 个音乐评论站，三层抓取 (RSS → HTML → Camoufox) + Kanban Swarm 评分推送 GitHub + Telegram
category: music
cron_job: ec5ea562d589（每天 04:00 北京时间）
author: hermes-agent
version: 7.0
license: MIT
created: 2026-05-07
updated: 2026-06-09
trigger_condition: cron 每天 04:00 自动，或手动 `hermes cron run ec5ea562d589`
metadata:
  hermes:
    tags: [music-reviews, kanban, fan-out, scraper, aggregator]
    related_skills: [kanban-worker, hermes-agent-skill-authoring]
---

# 架构 — 三层抓取 + Kanban Swarm

```
cron 04:00 → Step 0–4 (cron session)
   ↓
   ├─ Step 2: RSS (28 站, fast-rss-scrape.py, ~60s)
   ├─ Step 3: HTML (12 站, scrape_*.py, ~180s, 180s timeout)
   ├─ Step 4: merge_scraped.py → scraped_raw.json
   ↓
Step 5: kanban-swarm.py --confirm → 9 Camoufox workers (todo)
   ↓ cron session 退出
┌─ kanban 调度器接管 ────────────────────────┐
│ Root (done, 共享 blackboard)                │
│   ├─ 9 Camoufox workers (抓 9 站)         │
│   ├─ Verifier (todo, parent=所有 worker)   │
│   │    merge + 质量门 → gate pass/block    │
│   └─ Synthesizer (todo, parent=verifier)   │
│        评分 → 报告 → git push → Telegram   │
│        → 归档                               │
└────────────────────────────────────────────┘
```

---

# 优先级规则

每个站只分配一种抓取策略，按优先级从高到低：

1. **RSS** — `has_rss=True AND rss_url` 非空 → `fast-rss-scrape.py`
2. **HTML** — 在 `HTML_SCRIPT_IDS` 集合里（12 站）→ 对应 `scrape_*.py`
3. **Camoufox** — 剩余 `crawl_strategy=playwright_headless` → kanban worker

**实现位置**：
- RSS 筛选：`bin/fast-rss-scrape.py:load_sites()` 只看 `has_rss AND rss_url`
- HTML/Camoufox 分配：`bin/kanban-swarm.py:HTML_SCRIPT_IDS` 常量 + `get_sites()` 逻辑

---

# 站点分发表（51 总站 = 28 RSS + 12 HTML + 9 Camoufox + 3 skip，含 fluid_radio 归 RSS）

## 28 RSS（fast-rss-scrape.py 抓）

按 `sites.json` 顺序：
- the_wire, the_quietus, a_closer_listen, avant_music_news, bandcamp_daily, igloo_magazine
- fluid_radio（注：has_rss=True 但 crawl_strategy=skip；RSS 优先规则下仍走 RSS，feed 灌的是 2013-2022 历史存档，预期 0 条）
- icareifyoulisten, jazztimes, sequenza21, van_magazine, rhythm_passport, progarchives
- rest_is_noise_ph, attn_magazine, chain_dlk, hhv_mag, new_music_buff, jazz_journal
- five_against_four, modern_classical_music, the_classic_review, froots, prog_mistress
- side_line, post_punk_com, i_die_you_die, peek_a_boo_magazine

## 12 HTML（scrape_*.py 抓，并行 180s timeout）

| 站 | 脚本 | 备注 |
|---|---|---|
| all_about_jazz | scrape_all_about_jazz.py | Cloudflare 列表页只取 metadata，excerpt 空 |
| dark_entries_be | scrape_dark_entries.py | 比利时荷兰语暗潮/哥特/工业 |
| downbeat | scrape_downbeat.py | 传统专业爵士 |
| free_jazz_blog | scrape_free_jazz_blog.py | 自由爵士/先锋即兴 |
| jazz_trail | scrape_jazz_trail.py | 翻页多但 --days 1.5 会正确过滤 |
| mixmag_asia | scrape_mixmag_asia.py | 列表页 + 内联 excerpt |
| musique_machine | scrape_musique_machine.py | 电影/音乐混合，靠 (BLU-RAY/UHD/VOD/DVD) 过滤 |
| resident_advisor | scrape_resident_advisor.py | Cloudflare 列表页，excerpt 20-50 字 |
| sea_of_tranquility | scrape_sea_of_tranquility.py | urllib 直连（非 Camoufox），早停 5 条 |
| songlines | scrape_songlines.py | 180s timeout（120s 不足） |
| squids_ear | scrape_squids_ear.py | 极高产，单次 100+ 条；merger 截断不会丢 |
| wild_city | scrape_wild_city.py | 印度/南亚电子 |

## 9 Camoufox（kanban worker 抓）

按 `sites.json` 顺序（`crawl_strategy=playwright_headless` 且非 HTML_SCRIPT_IDS）：

| 站 | 备注 |
|---|---|
| boomkat | Cloudflare ASN 整段封锁，Camoufox fingerprint 2026-05-19 实测可绕过 |
| point_of_departure | 自由爵士/前卫/实验，点击 Current Issue 进入本期列表 |
| progressor | 冷门 prog/fusion |
| roots_world | 主页已迁移到 /rw/，HTML 抓取路径 |
| world_music_central | 全球 roots/融合 |
| bandwagon_asia | 新加坡/东南亚场景补充 |
| hear65 | 新加坡本地场景 |
| strangely_isolated_place | 柔和/空间感/后氛围 |
| truth_and_lies_music | 小而精的补充雷达 |

## 3 skip

- syrphe, textura, fluid_radio（注：fluid_radio 实际优先走 RSS，RSS feed 灌 2013-2022 历史，预期 0 条）

---

# 时间窗口 — 1.5 天 = 36 小时（硬约束）

**所有抓取源的统一 cutoff：1.5 天 = 36 小时 = `timedelta(days=1.5)` = `timedelta(hours=36)`。**

- `fast-rss-scrape.py` 默认 `--days 1.5`
- 12 个 HTML 脚本默认 `--days 1.5`
- Kanban worker body 显式传 `--days 1.5` 给 scrape 脚本
- Sea of Tranquility 早停 5 条连续 < cutoff

**禁止：**
- 自行计算 cutoff 日期（直接传 `--days 1.5`）
- RSS 走通后开浏览器"交叉验证"
- 翻超过前 2 页列表页

---

# 执行步骤

## Step 0 — 预检

```bash
# DB 完整性
python3 -c "
import sqlite3
c = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
print('DB_INTEGRITY:' + c.execute('PRAGMA integrity_check').fetchone()[0])
c.close()
"
# 期望: DB_INTEGRITY:ok

# Auth
bash /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/check-scraper-auth.sh

# Gateway
systemctl --user is-active hermes-gateway
# 期望: active
```

## Step 1 — 同步（仅 cron/自动化运行需要；交互式运行跳过）

```bash
cd /home/liyifan/music-record && git pull origin main

# SKILL.md 同步到 skill 目录
cp /home/liyifan/music-record/skills/music/music-daily-recs/SKILL.md \
   /home/liyifan/.hermes/skills/music/music-daily-recs/

# 脚本同步到 ~/.local/bin/ 和 skill 目录
mkdir -p /home/liyifan/.local/bin
for s in fast-rss-scrape.py merge_scraped.py process_reviews.py \
         generate_report.py kanban-swarm.py; do
  cp /home/liyifan/music-record/bin/$s /home/liyifan/.local/bin/
  cp /home/liyifan/music-record/bin/$s \
     /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/ 2>/dev/null || true
done

# HTML 12 脚本同步（cron 下也走 ~/.local/bin/）
for s in scrape_all_about_jazz.py scrape_dark_entries.py scrape_downbeat.py \
         scrape_free_jazz_blog.py scrape_jazz_trail.py scrape_mixmag_asia.py \
         scrape_musique_machine.py scrape_resident_advisor.py \
         scrape_sea_of_tranquility.py scrape_songlines.py scrape_squids_ear.py \
         scrape_wild_city.py; do
  cp /home/liyifan/music-record/bin/$s /home/liyifan/.local/bin/
done

# sites.json 同步
mkdir -p /home/liyifan/.minimax/music-sites
cp /home/liyifan/music-record/data/sites.json \
   /home/liyifan/.minimax/music-sites/
```

## Step 2 — RSS 批量抓取（28 站，~60s）

`fast-rss-scrape.py` 内部已设置 `socket.setdefaulttimeout(15)`（防 ProgArchives/The Wire/Rest Is Noise PH 挂起）：

```bash
DATE_DIR="/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"

python3 /home/liyifan/.local/bin/fast-rss-scrape.py \
  --days 1.5 \
  -o "$DATE_DIR/rss_merged.json"
```

**输出**：`rss_merged.json` — `{meta: {total, scraped_at, cutoff_date}, items: [...]}`
**实际跑 28 站**（含 fluid_radio；skip 站不参与 — fluid_radio 例外因为 has_rss=True 优先）

## Step 3 — HTML 并行抓取（12 站，~180s，180s timeout）

⚠️ **Hermes cron 环境**：shell `&`/`wait` 后台被拒，必须用 Python subprocess 方式：

```bash
DATE_DIR="/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"

cat > /tmp/run_html_scrapers.py << 'PYEOF'
#!/usr/bin/env python3
import subprocess, os, json, sys
from datetime import datetime

DATE_DIR = f"/home/liyifan/music-record/2026/{datetime.now().strftime('%m')}/{datetime.now().strftime('%Y-%m-%d')}"
SCRIPTS = [
    ("scrape_all_about_jazz", "all_about_jazz"),
    ("scrape_dark_entries", "dark_entries_be"),
    ("scrape_downbeat", "downbeat"),
    ("scrape_free_jazz_blog", "free_jazz_blog"),
    ("scrape_jazz_trail", "jazz_trail"),
    ("scrape_mixmag_asia", "mixmag_asia"),
    ("scrape_musique_machine", "musique_machine"),
    ("scrape_resident_advisor", "resident_advisor"),
    ("scrape_sea_of_tranquility", "sea_of_tranquility"),
    ("scrape_songlines", "songlines"),
    ("scrape_squids_ear", "squids_ear"),
    ("scrape_wild_city", "wild_city"),
]
os.makedirs(DATE_DIR, exist_ok=True)

procs = []
for script, site_id in SCRIPTS:
    out = os.path.join(DATE_DIR, f"{site_id}_reviews.json")
    cmd = ["timeout", "180", "python3",
           f"/home/liyifan/.local/bin/{script}.py",
           "--days", "1.5", "--out-dir", DATE_DIR]
    fout = open(out, "w")
    p = subprocess.Popen(cmd, stdout=fout, stderr=subprocess.DEVNULL)
    procs.append((p, site_id, fout))

for p, sid, fout in procs:
    try:
        p.wait(190)
    except subprocess.TimeoutExpired:
        p.kill()
    finally:
        fout.close()

for _, sid, _ in procs:
    out = os.path.join(DATE_DIR, f"{sid}_reviews.json")
    try:
        d = json.load(open(out))
        n = len(d.get("items", []))
        print(f"  {sid}: {n} 条", file=sys.stderr)
    except Exception as e:
        print(f"  {sid}: FAILED ({e})", file=sys.stderr)
PYEOF

python3 /tmp/run_html_scrapers.py 2>&1
```

**输出**：12 个 `{site_id}_reviews.json`，schema 与 RSS 一致 `{meta, items}`

## Step 4 — 合并 → scraped_raw.json

```bash
cd /home/liyifan/music-record
python3 /home/liyifan/.local/bin/merge_scraped.py \
  --date-dir "$(pwd)/2026/$(date +%m)/$(date +%Y-%m-%d)" \
  -o scraped_raw.json
```

**输出**：`scraped_raw.json` — `{meta: {total, merged_from, scraped_at}, items: [...]}`

## Step 5 — 创建 Kanban Swarm

```bash
# dry run 看会派 9 个 worker
python3 /home/liyifan/music-record/bin/kanban-swarm.py

# 确认创建
python3 /home/liyifan/music-record/bin/kanban-swarm.py --confirm
```

`kanban-swarm.py` 创建：
```
Root (done, idempotency_key=music-recs-swarm-YYYY-MM-DD)
  ├─ 9 Camoufox workers (ready)
  ├─ Verifier (todo, parent=所有 worker)
  └─ Synthesizer (todo, parent=verifier)
```

**Step 5 完成后，cron session 立即结束**。kanban scheduler 自动接手。

---

# Kanban Swarm 内部（worker → verifier → synthesizer）

## Workers（9 个，scraper profile）

worker body 包含：
- 站点 URL + RSS URL（**强制 RSS 优先检查**：有 RSS 命中则跳过浏览器）
- 时间窗口硬约束 `--days 1.5`
- 输出 schema `{meta, items}` + 必须含 `body` 字段
- 180-iteration Camoufox budget
- 翻前 2 页列表页

详见 `bin/kanban-swarm.py:build_scraper_body()`。

## Verifier（1 个，scraper profile）

`VERIFIER_BODY` 在 `bin/kanban-swarm.py`，body 步骤：

1. `merge_scraped.py` 合并所有数据 → `scraped_raw.json`
2. 验证：`scraped_raw.json` 含 `site_id` 字段、`items > 0`
3. 通过 → `kanban_complete(metadata={gate: pass, total_items: N})`
4. 失败 → `kanban_block(reason="...")`

## Synthesizer（1 个，scraper profile）

`SYNTHESIZER_BODY` 在 `bin/kanban-swarm.py`，body 步骤：

1. `process_reviews.py --max-workers 3`（MiniMax rate-limit 安全值）→ `processed.json`
2. `generate_report.py` → `recommend/{DATE}.md`
3. `git push origin main`（如失败，记录实际错误）
4. Telegram 推送（≤4000 字符全文，否则精简 + GitHub 链接）
5. `hermes kanban archive` 归档本轮 scraper 任务
6. `kanban_complete`

---

# 触发方式

| 触发 | 命令 |
|---|---|
| 自动 | cron `ec5ea562d589` 每天 04:00 |
| 手动 | `hermes cron run ec5ea562d589` |

---

# 监控

```bash
# 任务状态分布
hermes kanban list | grep "scrape:" | awk '{print $2}' | sort | uniq -c | sort -rn

# 详细状态
hermes kanban show <task_id>

# 实时日志
hermes kanban tail <task_id>
```

---

# 恢复

| 症状 | 处理 |
|---|---|
| cron 未触发 | `hermes cron status`；`journalctl --user -u hermes-gateway` |
| gateway stopped | `hermes gateway run --replace` |
| worker 卡 ready | `hermes kanban dispatch` |
| worker 状态 running 但无进程 | `hermes kanban complete <id>` |
| verifier gate=block | `hermes kanban show <verifier_id>` 看日志；手动重跑 `merge_scraped.py` 后 `hermes kanban edit <verifier_id> --add-metadata '{"gate":"pass"}'` |
| MiniMax rate-limit 429 | `process_reviews.py --max-workers 3`（已默认）→ 2 |
| 跨日重复 swarm | 自动 idempotency：`music-recs-swarm-YYYY-MM-DD` |

---

# 评分（v3 — LLM 直打）

`process_reviews.py` 用 Minimax-M3（Anthropic SDK，api.minimaxi.com）。评分+中文总结同一次 API 调用，线程池 3 并发。

## 6 维评分（prompt 内）

| 维度 | 影响 |
|---|---|
| 口味匹配度（最高权重） | 1-10：实验/前卫/爵士/电子/世界/暗潮 → 高 |
| 创新性独特性 | 加减分 |
| 跨领域融合 | 加分 |
| 地区特色 | +1 ~ +2 |
| 主流降权 | -1 ~ -2 |
| 评论质量 | 内容短(<200字)或新闻稿 → -1 |

## 输出 schema

```json
{"total_score": 1-10, "cn_summary": "150-300 字"}
```

3 层 JSON 解析 fallback（直接/反引号/regex）。

---

# 关键路径

| 用途 | 路径 |
|---|---|
| RSS 抓取 | `/home/liyifan/music-record/bin/fast-rss-scrape.py` |
| HTML 12 脚本 | `/home/liyifan/music-record/bin/scrape_*.py` |
| 合并 | `/home/liyifan/music-record/bin/merge_scraped.py` |
| 评分 | `/home/liyifan/music-record/bin/process_reviews.py` |
| 报告 | `/home/liyifan/music-record/bin/generate_report.py` |
| Swarm 创建 | `/home/liyifan/music-record/bin/kanban-swarm.py` |
| 站点配置 | `/home/liyifan/.minimax/music-sites/sites.json` |
| Skill | `/home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md` |
| GitHub | https://github.com/pty819/music-record |
| Camoufox 服务 | `systemctl --user hermes-camoufox.service` |
| Cron job ID | `ec5ea562d589` |

---

# Pitfalls（结构性 + 会再发生）

| 症状 | 原因 | 处理 |
|---|---|---|
| **Camoufox 静默退出** | 进程消失 task 留 running | `hermes kanban complete <id>` 后看 `ps aux \| grep <id>` |
| **Iteration budget exhausted** | Squid's Ear 一次 100+ 条超出 90 轮 | force-complete；merger 截断不丢数据 |
| **Songlines 180s timeout 不够** | 40+ 条需 120-180s | 已统一 `timeout 180`；如仍超时升 240s |
| **feedparser 挂起** | Cloudflare 保护 | `fast-rss-scrape.py` 顶部已 `socket.setdefaulttimeout(15)` |
| **MiniMax rate-limit 429** | 5 并发过高 | `--max-workers 3`（已默认） |
| **Cron session 0 输出** | prompt 引用旧 skill 步骤 | `hermes cron run <id>` 手动触发；查 `jobs.json` |
| **Verifier 卡 todo** | 等待所有 worker done | 正常；若都已 done 仍 todo → `hermes kanban dispatch` |
| **Synthesizer 卡 todo** | verifier metadata.gate ≠ pass | 手动 `hermes kanban edit <verifier_id> --add-metadata '{"gate":"pass"}'` |
