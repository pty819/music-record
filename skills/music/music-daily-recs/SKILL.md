---
name: music-daily-recs
description: 每日巡检 51 个音乐评论站，三层抓取 (RSS → HTML → Camoufox) + Kanban Swarm 评分推送 GitHub + Telegram
category: music
cron_job: ec5ea562d589（每天 04:00 北京时间）
author: hermes-agent
version: 7.3
license: MIT
created: 2026-05-07
updated: 2026-06-10
trigger_condition: cron 每天 04:00 自动，或手动 `hermes cron run ec5ea562d589`
metadata:
  hermes:
    tags: [music-reviews, kanban, fan-out, scraper, aggregator]
    related_skills: [kanban-worker, hermes-agent-skill-authoring]
---

# 架构 — 三层抓取 + Kanban Swarm

```
cron 04:00 → Step 0–5 (cron session)
   │
   ├─ Step 2: RSS    (29 站, 8 线程并发, 60-120s)
   ├─ Step 3: HTML   (16 站子进程并发, ~150s, → html_reviews.json)
   ├─ Step 4: merge  (rss + html + camoufox → scraped_raw.json)
   ├─ Step 5: kanban-swarm.py --confirm
   │
   ↓ cron session 退出，kanban 调度器接管
┌─────────────────────────────────────────────┐
│ Root (done, shared blackboard)              │
│   ├─ 4 Camoufox workers (boomkat, PoD,     │
│   │    progressor, wild_city)               │
│   ├─ Verifier (todo, parent=workers+root)   │
│   │    merge_scraped.py + 质量门            │
│   └─ Synthesizer (todo, parent=verifier)    │
│        评分 → 报告 → git push → Telegram    │
│        → 归档                                │
└─────────────────────────────────────────────┘
```

---

# 站点分发（51 站 = 29 RSS + 16 HTML + 4 Camoufox + 2 skip）

优先级：RSS > HTML > Camoufox > skip。每个站只走一层。

| 层 | 数量 | 实现 |
|---|---|---|
| RSS | 29 | `fast-rss-scrape.py` — `has_rss=True AND rss_url` 非空的站 |
| HTML | 16 | `scrape_html_parallel.py` — `HTML_SCRIPT_IDS` 集合里的站 |
| Camoufox | 4 | `kanban-swarm.py` — 剩余站（无 RSS、非 HTML、非 skip） |
| skip | 2 | syrphe, textura（fluid_radio 归 RSS 因为 has_rss=True） |

**代码位置**：
- RSS 筛选：`bin/fast-rss-scrape.py:load_sites()`
- HTML/Camoufox 分配：`bin/kanban-swarm.py:HTML_SCRIPT_IDS` + `get_sites()`

## 29 RSS

the_wire, the_quietus, a_closer_listen, avant_music_news, bandcamp_daily, igloo_magazine, fluid_radio, icareifyoulisten, jazztimes, sequenza21, van_magazine, rhythm_passport, progarchives, rest_is_noise_ph, attn_magazine, chain_dlk, hhv_mag, new_music_buff, jazz_journal, five_against_four, modern_classical_music, the_classic_review, froots, prog_mistress, side_line, post_punk_com, i_die_you_die, peek_a_boo_magazine

注：fluid_radio 的 feed 灌的是 2013-2022 历史存档，预期 0 条新内容。

## 16 HTML

| 站 | 脚本 | 备注 |
|---|---|---|
| all_about_jazz | scrape_all_about_jazz.py | Cloudflare 列表页 |
| bandwagon_asia | scrape_bandwagon_asia.py | 新加坡/东南亚 |
| dark_entries_be | scrape_dark_entries.py | 暗潮/哥特/工业 |
| downbeat | scrape_downbeat.py | 爵士 |
| free_jazz_blog | scrape_free_jazz_blog.py | 自由爵士/先锋 |
| hear65 | scrape_hear65.py | 新加坡本地 |
| jazz_trail | scrape_jazz_trail.py | --max-pages 3 控速 |
| mixmag_asia | scrape_mixmag_asia.py | 列表页 + excerpt |
| musique_machine | scrape_musique_machine.py | 电影/音乐混合 |
| resident_advisor | scrape_resident_advisor.py | Cloudflare |
| roots_world | scrape_roots_world.py | curl 直连 |
| sea_of_tranquility | scrape_sea_of_tranquility.py | urllib 直连，早停 5 条 |
| songlines | scrape_songlines.py | 180s timeout |
| squids_ear | scrape_squids_ear.py | 极高产 100+ 条 |
| strangely_isolated_place | scrape_strangely_isolated_place.py | urllib 优先 |
| truth_and_lies_music | scrape_truth_and_lies_music.py | 小而精 |
| world_music_central | scrape_world_music_central.py | 全球 roots/融合 |

## 4 Camoufox（kanban worker，需 Camoufox 服务）

| 站 | 备注 |
|---|---|
| boomkat | Cloudflare ASN 封锁，脚本调 Camoufox REST API |
| point_of_departure | JS 渲染站，脚本调 Camoufox REST API |
| progressor | 冷门 prog/fusion，无独立 scrape 脚本 |
| wild_city | 印度/南亚电子，脚本调 Camoufox REST API |

## 2 skip

syrphe, textura

---

# 时间窗口 — 1.5 天 = 36 小时（硬约束）

所有抓取源统一 cutoff：`--days 1.5`。

- `fast-rss-scrape.py` 默认 `--days 1.5`
- 16 个 HTML 脚本全部接受 `--days 1.5`
- Kanban worker body 显式传 `--days 1.5`

**禁止**：自行计算 cutoff 日期、RSS 走通后开浏览器"交叉验证"、翻超过前 2 页列表页。

---

# 执行步骤

## Step 0 — 预检

```bash
# DB 完整性
python3 -c "import sqlite3; c=sqlite3.connect('/home/liyifan/.hermes/kanban.db'); print('DB:' + c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"

# Gateway
systemctl --user is-active hermes-gateway

# 网络
curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://daily.bandcamp.com/feed
# 期望 200。000 = VPN 断连
```

## Step 1 — 同步

```bash
cd /home/liyifan/music-record && git pull origin main

# scripts/ 已是 symlink → ~/music-record/bin/，无需复制
# 只需同步 SKILL.md
cp skills/music/music-daily-recs/SKILL.md ~/.hermes/skills/music/music-daily-recs/
```

## Step 2 — RSS 批量抓取（29 站，300-700s）

8 线程并发，每线程 30s socket timeout。实测 60-120s 完成。

```bash
DATE_DIR="/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"

python3 bin/fast-rss-scrape.py --days 1.5 -o "$DATE_DIR/rss_merged.json"
```

输出：`rss_merged.json` — `{meta: {total, scraped_at, cutoff_date}, items: [...]}`

## Step 3 — HTML 并行抓取（16 站，~180s）

```bash
python3 bin/scrape_html_parallel.py \
  --out-dir "$DATE_DIR" --days 1.5 --timeout 180
```

`scrape_html_parallel.py` 并行起 17 个子进程。一个失败不影响其他。
sea_of_tranquility 走 `--out-dir` 模式（自写文件），其余走 stdout 重定向。

输出：17 个 `{site_id}_reviews.json`

## Step 4 — 合并

```bash
cd /home/liyifan/music-record
python3 bin/merge_scraped.py \
  --date-dir "$DATE_DIR" -o scraped_raw.json
```

输出：`scraped_raw.json` — `{meta: {total, merged_from, scraped_at}, items: [...]}`

## Step 5 — 创建 Kanban Swarm

```bash
python3 /home/liyifan/music-record/bin/kanban-swarm.py --confirm
```

创建：
```
Root (done, idempotency_key=music-recs-swarm-YYYY-MM-DD)
  ├─ Camoufox workers (4 个: boomkat, PoD, progressor, wild_city)
  ├─ Verifier (todo, parent=workers+root)
  └─ Synthesizer (todo, parent=verifier)
```

**cron session 到此结束。** kanban scheduler 接管后续。

---

# Kanban Swarm 内部

## Camoufox Workers（4 个）

由 kanban-swarm.py 自动创建。每个 worker 的 body 包含站点 URL、`--days 1.5` 约束、180 iteration budget。worker 完成后输出 `_reviews.json`。

## Verifier

body 步骤（`VERIFIER_BODY` in kanban-swarm.py）：
1. `merge_scraped.py` 合并 RSS + HTML + Camoufox 数据 → `scraped_raw.json`
2. 验证 `items > 0` 且含 `site_id` 字段
3. 通过 → `kanban_complete(metadata={gate: pass, total_items: N})`
4. 失败 → `kanban_block(reason=...)`

## Synthesizer

body 步骤（`SYNTHESIZER_BODY` in kanban-swarm.py）：
1. `process_reviews.py --max-workers 3` → `processed.json`（评分 + 中文总结）
2. `generate_report.py` → `recommend/{DATE}.md`
3. `git push origin main`
4. Telegram 推送（≤4000 字符全文，否则精简 + GitHub 链接）
5. `hermes kanban archive` 归档本轮任务
6. `kanban_complete`

---

# 评分（v3 — LLM 直打）

`process_reviews.py` 用 hy3-preview (腾讯云 Anthropic 兼容)（Anthropic SDK，api.lkeap.cloud.tencent.com）。评分+中文总结同一次 API 调用，线程池 3 并发。

6 维评分：口味匹配度（最高权重）、创新性、跨领域融合、地区特色、主流降权、评论质量。

输出 schema：`{"total_score": 1-10, "cn_summary": "150-300 字"}`

---

# 触发方式

| 触发 | 命令 |
|---|---|
| 自动 | cron `ec5ea562d589` 每天 04:00 |
| 手动 | `hermes cron run ec5ea562d589` |

---

# 监控

```bash
hermes kanban list | grep "$(date +%Y-%m-%d)"
# 期望：Swarm done + Verifier done + Synthesizer done
```

---

# 验证当日执行（事后审计）

当用户问"今天是不是正确执行了"，按以下步骤逐层验证，**每一步都要跑命令拿真实数据**：

## 1. 确认 cron 用了哪个版本

```bash
latest=$(ls -t ~/.hermes/cron/output/ec5ea562d589/ | head -1)
grep -m1 "version:" ~/.hermes/cron/output/ec5ea562d589/$latest
```

如果 version 不是最新，说明 cron 用了旧版。

## 2. 检查各层产出

```bash
DATE_DIR="/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)"

# RSS
python3 -c "import json; d=json.load(open('$DATE_DIR/rss_merged.json')); print(f'RSS: {d[\"meta\"][\"total\"]} 条')"

# HTML: 每个文件
for f in $DATE_DIR/*_reviews.json; do
  site=$(basename "$f" _reviews.json)
  size=$(stat -c%s "$f")
  count=$(python3 -c "import json; print(len(json.load(open('$f')).get('items',[])))" 2>/dev/null || echo "ERR")
  echo "  $site: ${size}B, items=$count"
done

# Merge
python3 -c "import json; d=json.load(open('$DATE_DIR/scraped_raw.json')); print(f'Merge: {d[\"meta\"][\"total\"]} 条 from {list(d[\"meta\"].get(\"merged_from\",{}).keys())}')"

# Processed
python3 -c "import json; d=json.load(open('$DATE_DIR/processed.json')); print(f'Processed: {len(d) if isinstance(d,list) else len(d.get(\"items\",[]))} 条')"
```

## 3. 确认 git push + 报告

```bash
cd /home/liyifan/music-record
git log --oneline --since="$(date +%Y-%m-%d)" | grep "recommend\|daily"
ls -la recommend/$(date +%Y-%m-%d).md
```

## 4. 确认 Kanban 全链路完成

```bash
hermes kanban list | grep "$(date +%Y-%m-%d)"
```

---

# 恢复

| 症状 | 处理 |
|---|---|
| cron 未触发 | `hermes cron status`；`journalctl --user -u hermes-gateway` |
| gateway stopped | `hermes gateway run --replace` |
| worker 卡 ready | `hermes kanban dispatch` |
| worker running 但无进程 | `hermes kanban complete <id>` |
| verifier gate=block | `hermes kanban show <verifier_id>` 看日志；手动重跑 merge 后 `hermes kanban edit <verifier_id> --add-metadata '{"gate":"pass"}'` |
| MiniMax 429 | `process_reviews.py --max-workers 3` → 降 2 |
| 跨日重复 swarm | 自动 idempotency：`music-recs-swarm-YYYY-MM-DD` |
| 全天推荐丢失 | 一个 worker blocked → verifier 永远 todo → synthesizer 永远 todo。`hermes kanban list | grep blocked` → `hermes kanban complete <id>` 解锁 |

---

# 关键路径

| 用途 | 路径 |
|---|---|
| RSS 抓取 | `bin/fast-rss-scrape.py` |
| HTML 16 脚本 | `bin/scrape_*.py`（不含 scrape_wild_city.py） |
| HTML 并行 wrapper | `bin/scrape_html_parallel.py` |
| 合并 | `bin/merge_scraped.py` |
| 评分 | `bin/process_reviews.py` |
| 报告 | `bin/generate_report.py` |
| Swarm 创建 | `bin/kanban-swarm.py` |
| 站点配置 | `data/sites.json`（唯一源，git 管理） |
| Skill | `~/.hermes/skills/music/music-daily-recs/SKILL.md` |
| Camoufox 服务 | `systemctl --user hermes-camoufox.service` |
| Cron job ID | `ec5ea562d589` |
| GitHub | https://github.com/pty819/music-record |

---

# Pitfalls

| 症状 | 原因 | 处理 |
|---|---|---|
| **scrape 脚本不认 --days** | parallel scraper 统一传 `--days 1.5`，但有些脚本只认 `--hours` 或 `--ref-date` → rc=2 | 脚本必须加 `--days` 支持。新脚本上线前 `--help` 验证 |
| **stdout 模式脚本不输出到 stdout** | 脚本只 `json.dump(f)` 写文件不 `print()` → parallel scraper 捕获 0B | stdout 模式必须有 `print(json.dumps(result))` |
| **wild_city 归类错误** | 脚本调 `CAMOFOX_BASE` REST API 但被放进 HTML_SCRIPT_IDS | 新站上线前 `grep CAMOFOX_BASE` 确认依赖 |
| **Cron 用旧版 skill** | commit 在 cron 之后 → git pull 拉不到新代码 | 改完立即 `git push`；重大改动手动 `hermes cron run` 验证 |
| **RSS 全部 0 条** | VPN TLS 握手超时（15s 太紧） | `socket.setdefaulttimeout(30)` + terminal timeout=900 |
| **HTML 全部 0B + Camoufox 500** | Meta VPN 断连 | `curl -s -o /dev/null -w "%{http_code}" https://daily.bandcamp.com/feed` 检查；RSS 可能仍可用 |
| **Verifier 卡 todo** | 等待所有 worker done | 正常；若都 done 仍 todo → `hermes kanban dispatch` |
| **Synthesizer 卡 todo** | verifier gate ≠ pass | `hermes kanban edit <verifier_id> --add-metadata '{"gate":"pass"}'` |
| **Camoufox 静默退出** | 进程消失 task 留 running | `hermes kanban complete <id>` |
| **Songlines 180s timeout** | 40+ 条需 120-180s | 如仍超时升 240s |
| **MiniMax 429** | 并发过高 | `--max-workers 3`（已默认） |
| **bandwagon_asia/strangely_isolated_place 间歇 rc=2** | 17 脚本并行时资源竞争（单独跑正常） | merger 容忍单脚本失败 |
