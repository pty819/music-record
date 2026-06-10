---
name: music-daily-recs
description: 每日巡检 48 个音乐评论站，三层抓取 (RSS → HTML → Camoufox) + Kanban Swarm 评分推送 GitHub + Telegram
category: music
cron_job: ec5ea562d589（每天 04:00 北京时间）
author: hermes-agent
version: 7.2
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
cron 04:00 → Step 0–4 (cron session)
   ↓
   ├─ Step 2: RSS (28 站, fast-rss-scrape.py, 实际 300-700s，terminal timeout=900)
   ├─ Step 3: HTML (17 站, scrape_*.py, ~180s, 180s timeout)
   ├─ Step 4: merge_scraped.py → scraped_raw.json
   ↓
Step 5: kanban-swarm.py --confirm → 4 Camoufox workers + verifier + synthesizer
   ↓ cron session 退出
┌─ kanban 调度器接管 ────────────────────────┐
│ Root (done, 共享 blackboard)                │
│   ├─ 4 Camoufox workers               │
│   ├─ Verifier (todo, parent=workers)   │
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
2. **HTML** — 在 `HTML_SCRIPT_IDS` 集合里（17 站）→ 对应 `scrape_*.py`
3. **Camoufox** — 剩余 `crawl_strategy=playwright_headless` → kanban worker

**实现位置**：
- RSS 筛选：`bin/fast-rss-scrape.py:load_sites()` 只看 `has_rss AND rss_url`
- HTML/Camoufox 分配：`bin/kanban-swarm.py:HTML_SCRIPT_IDS` 常量 + `get_sites()` 逻辑

---

# 站点分发表（51 总站 = 27 RSS + 17 HTML + 4 Camoufox + 3 skip，含 fluid_radio 归 RSS）

## 28 RSS（fast-rss-scrape.py 抓）

按 `sites.json` 顺序：
- the_wire, the_quietus, a_closer_listen, avant_music_news, bandcamp_daily, igloo_magazine
- fluid_radio（注：has_rss=True 但 crawl_strategy=skip；RSS 优先规则下仍走 RSS，feed 灌的是 2013-2022 历史存档，预期 0 条）
- icareifyoulisten, jazztimes, sequenza21, van_magazine, rhythm_passport, progarchives
- rest_is_noise_ph, attn_magazine, chain_dlk, hhv_mag, new_music_buff, jazz_journal
- five_against_four, modern_classical_music, the_classic_review, froots, prog_mistress
- side_line, post_punk_com, i_die_you_die, peek_a_boo_magazine

## 17 HTML（scrape_*.py 抓，并行 180s timeout）

| 站 | 脚本 | 备注 |
|---|---|---|
| all_about_jazz | scrape_all_about_jazz.py | Cloudflare 列表页只取 metadata，excerpt 空 |
| bandwagon_asia | scrape_bandwagon_asia.py | 新加坡/东南亚场景补充 |
| dark_entries_be | scrape_dark_entries.py | 比利时荷兰语暗潮/哥特/工业 |
| downbeat | scrape_downbeat.py | 传统专业爵士 |
| free_jazz_blog | scrape_free_jazz_blog.py | 自由爵士/先锋即兴 |
| hear65 | scrape_hear65.py | 新加坡本地场景 |
| jazz_trail | scrape_jazz_trail.py | 翻页多但 --days 1.5 会正确过滤 |
| mixmag_asia | scrape_mixmag_asia.py | 列表页 + 内联 excerpt |
| musique_machine | scrape_musique_machine.py | 电影/音乐混合，靠 (BLU-RAY/UHD/VOD/DVD) 过滤 |
| resident_advisor | scrape_resident_advisor.py | Cloudflare 列表页，excerpt 20-50 字 |
| roots_world | scrape_roots_world.py | curl 直连 |
| sea_of_tranquility | scrape_sea_of_tranquility.py | urllib 直连，早停 5 条 |
| songlines | scrape_songlines.py | 180s timeout（120s 不足） |
| squids_ear | scrape_squids_ear.py | 极高产，单次 100+ 条；merger 截断不会丢 |
| strangely_isolated_place | scrape_strangely_isolated_place.py | urllib 优先，Camoufox fallback |
| truth_and_lies_music | scrape_truth_and_lies_music.py | 小而精的补充雷达 |
| wild_city | scrape_wild_city.py | **⚠️ 依赖 Camoufox REST API，非纯 HTTP**；应归 Camoufox 组 |
| world_music_central | scrape_world_music_central.py | 全球 roots/融合 |

## 4 Camoufox（kanban worker 抓，需 Camoufox 服务）

| 站 | 备注 |
|---|---|
| boomkat | Cloudflare ASN 封锁，脚本调 Camoufox REST API |
| point_of_departure | JS 渲染站，脚本调 Camoufox REST API |
| progressor | 冷门 prog/fusion，无独立 scrape 脚本 |
| wild_city | 印度/南亚电子，脚本调 Camoufox REST API |

## 3 skip

- syrphe, textura, fluid_radio（注：fluid_radio 实际优先走 RSS，RSS feed 灌 2013-2022 历史，预期 0 条）

---

# 时间窗口 — 1.5 天 = 36 小时（硬约束）

**所有抓取源的统一 cutoff：1.5 天 = 36 小时 = `timedelta(days=1.5)` = `timedelta(hours=36)`。**

- `fast-rss-scrape.py` 默认 `--days 1.5`
- 18 个 HTML 脚本默认 `--days 1.5`
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

# 网络连通性（Meta VPN 路由检查）
curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://daily.bandcamp.com/feed
# 期望: 200。若 000 → Meta VPN (28.0.0.x) 可能断连，HTML/Camoufox 全部会失败
# 诊断: curl -v --max-time 5 https://www.google.com 看是否 SSL_ERROR_SYSCALL

# feedparser 连通性（VPN TLS 握手慢，需 30s）
python3 -c "import feedparser,socket; socket.setdefaulttimeout(30); print(len(feedparser.parse('https://daily.bandcamp.com/feed').entries))"
# 期望: >0。若超时 → VPN TLS 太慢，需加 socket timeout 或等网络恢复
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

# HTML 18 脚本同步（cron 下也走 ~/.local/bin/）
for s in scrape_all_about_jazz.py scrape_bandwagon_asia.py scrape_dark_entries.py \
         scrape_downbeat.py scrape_free_jazz_blog.py scrape_hear65.py \
         scrape_jazz_trail.py scrape_mixmag_asia.py scrape_musique_machine.py \
         scrape_resident_advisor.py scrape_roots_world.py \
         scrape_sea_of_tranquility.py scrape_songlines.py scrape_squids_ear.py \
         scrape_strangely_isolated_place.py scrape_truth_and_lies_music.py \
         scrape_wild_city.py scrape_world_music_central.py; do
  cp /home/liyifan/music-record/bin/$s /home/liyifan/.local/bin/
done

# sites.json 同步
mkdir -p /home/liyifan/.minimax/music-sites
cp /home/liyifan/music-record/data/sites.json \
   /home/liyifan/.minimax/music-sites/
```

## Step 2 — RSS 批量抓取（28 站，实际 300-600s）

`fast-rss-scrape.py` 内部已设置 `socket.setdefaulttimeout(30)`（Meta VPN 下 TLS 握手 8-10s，15s 太紧导致大部分站超时）。**28 站 × 30s 超时 = 840s 理论上限；实测多站 20-28s，总耗时 300-700s。terminal 必须设 `timeout=900`。** 详见 `references/feedparser-vpn-timeout.md`。

```bash
DATE_DIR="/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"

python3 /home/liyifan/.local/bin/fast-rss-scrape.py \
  --days 1.5 \
  -o "$DATE_DIR/rss_merged.json"
```

**终端 timeout=900**（VPN 下慢站 25-30s/站，最坏 840s）。

**输出**：`rss_merged.json` — `{meta: {total, scraped_at, cutoff_date}, items: [...]}`
**实际跑 28 站**（含 fluid_radio；skip 站不参与 — fluid_radio 例外因为 has_rss=True 优先）

## Step 3 — HTML 并行抓取（17 站，~180s，180s timeout）

⚠️ **Hermes cron 环境**：shell `&`/`wait` 后台被拒，必须用 Python subprocess 方式：

```bash
DATE_DIR="/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"

python3 /home/liyifan/.local/bin/scrape_html_parallel.py \
  --out-dir "$DATE_DIR" \
  --days 1.5 \
  --timeout 180
```

**Wrapper 设计**（`bin/scrape_html_parallel.py`，已 commit）：
- 并行起 18 个 scrape 子进程，per-scraper timeout 180s
- 17 个走 stdout 重定向到 `<site_id>_reviews.json`
- `scrape_sea_of_tranquility` 走 `--out-dir` 模式（它自写文件，stdout 是日志）
- 一个 scraper 失败不影响其他（`return 0` 让 pipeline 继续 Step 4）
- **不再 heredoc 写 Python**——彻底消除 cron session 缩进丢失风险

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
# dry run 看会派的 worker
python3 /home/liyifan/music-record/bin/kanban-swarm.py

# 确认创建
python3 /home/liyifan/music-record/bin/kanban-swarm.py --confirm
```

`kanban-swarm.py` 创建：
```
Root (done, idempotency_key=music-recs-swarm-YYYY-MM-DD)
  ├─ Verifier (todo, parent=root)
  └─ Synthesizer (todo, parent=verifier)
```

**Step 5 完成后，cron session 立即结束**。kanban scheduler 自动接手。

---

# Kanban Swarm 内部（verifier → synthesizer）

## Workers（4 个：boomkat, point_of_departure, progressor, wild_city）

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

# 验证当日执行（事后审计）

当用户问"今天是不是正确执行了"，按以下步骤逐层验证，**每一步都要跑命令拿真实数据**：

## 1. 确认 cron 用了哪个版本

```bash
# 最新 cron 输出文件
ls -t ~/.hermes/cron/output/ec5ea562d589/ | head -1
# 看 version 字段
grep -m1 "version:" ~/.hermes/cron/output/ec5ea562d589/<latest>.md
```

如果 version 不是最新（如显示 7.0 而非 7.2），说明 cron 用了旧版——后续步骤的数据会反映旧版行为。

## 2. 检查各层产出文件

```bash
DATE_DIR="/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)"

# RSS: 站数 + 条目数
python3 -c "
import json; d=json.load(open('$DATE_DIR/rss_merged.json'))
sites=set(i['site_id'] for i in d['items'])
print(f'RSS: {len(sites)} 站, {len(d[\"items\"])} 条')
"

# HTML: 每个文件的条目数（0 字节 = 脚本失败）
for f in $DATE_DIR/*_reviews.json; do
  site=$(basename "$f" _reviews.json)
  size=$(stat -c%s "$f")
  count=$(python3 -c "import json; print(len(json.load(open('$f')).get('items',[])))" 2>/dev/null || echo "ERR")
  echo "  $site: ${size}B, items=$count"
done

# Merge: 总数 + 来源分布
python3 -c "
import json; d=json.load(open('$DATE_DIR/scraped_raw.json'))
print(f'Merge: {d[\"meta\"][\"total\"]} 条, merged_from: {d[\"meta\"].get(\"merged_from\",{})}')
"

# Processed: 评分完成数
python3 -c "
import json; d=json.load(open('$DATE_DIR/processed.json'))
print(f'Processed: {len(d) if isinstance(d,list) else len(d.get(\"items\",[]))} 条')
"
```

## 3. 确认 git push + 报告存在

```bash
cd /home/liyifan/music-record
git log --oneline --since="$(date +%Y-%m-%d)" | grep "recommend\|daily"
ls -la recommend/$(date +%Y-%m-%d).md
```

## 4. 确认 Kanban 全链路完成

```bash
hermes kanban list | grep "$(date +%Y-%m-%d)"
# 期望：Swarm done + Verifier done + Synthesizer done
# 如果有 blocked/running → 看恢复表
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
| HTML 18 脚本 | `/home/liyifan/music-record/bin/scrape_*.py` |
| 合并 | `/home/liyifan/music-record/bin/merge_scraped.py` |
| 评分 | `/home/liyifan/music-record/bin/process_reviews.py` |
| 报告 | `/home/liyifan/music-record/bin/generate_report.py` |
| Swarm 创建 | `/home/liyifan/music-record/bin/kanban-swarm.py` |
| 站点配置 | `/home/liyifan/.minimax/music-sites/sites.json` |
| Skill | `/home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md` |
| VPN timeout 参考 | `references/feedparser-vpn-timeout.md` |
| 站点分类方法 | `references/site-classification-methodology.md` |
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
| **feedparser 挂起** | Cloudflare 保护 | `fast-rss-scrape.py` 顶部已 `socket.setdefaulttimeout(30)`。VPN 诊断见 `references/feedparser-vpn-timeout-diagnosis.md` |
| **scrape 脚本不认 --days 参数** | scrape_html_parallel.py 统一传 `--days 1.5`，但 hear65(`--hours`)、roots_world(`--ref-date`)、world_music_central(`--hours`) 不接受 → rc=2 | 每个脚本必须加 `--days` 参数（2026-06-10 已修 hear65/roots_world/world_music_central）。新增脚本上线前必跑 `scrape_html_parallel.py --out-dir /tmp/test` 验证 rc=0 |
| **stdout 模式脚本不输出到 stdout** | world_music_central/truth_and_lies_music 成功时只写文件(`json.dump(f)`)不 `print(json)` → parallel scraper 捕获 0B | stdout 模式脚本必须有 `print(json.dumps(result))`。检查方法：`python3 scrape_X.py --days 1.5 > /dev/null` 看 exit code，`> /tmp/test.json && stat` 看文件大小 |
| **HTML_SCRIPT_IDS 缺站（已修 v7.2）** | ~~bin/ 有 20 个 scrape_*.py 但 HTML_SCRIPT_IDS 只注册 12 个~~ → 已修：17 个 HTML + 4 Camoufox（boomkat/PoD 调 REST API，progressor 无脚本）。注意 dark_entries 脚本命名不匹配（scrape_dark_entries.py vs 注册的 dark_entries_be） | 已修 2026-06-10。boomkat + point_of_departure 确认依赖 Camoufox REST API（grep `CAMOFOX_BASE`），不能归 HTML |
| **MiniMax rate-limit 429** | 5 并发过高 | `--max-workers 3`（已默认） |
| **Cron 用旧版 skill** | commit 在 cron 之后 → Step 1 `git pull` 拉不到新代码 → 整轮用旧版 SKILL.md/脚本 | 改完务必在下次 cron 前 push；或手动 `hermes cron run` 验证。2026-06-10 实例：v7.2 commit 在 04:28 cron 之后，当天仍跑 v7.0（RSS 15s timeout、HTML 12 站、Camoufox 9 worker） |
| **Cron session 0 输出** | prompt 引用旧 skill 步骤 | `hermes cron run <id>` 手动触发；查 `jobs.json` |
| **Verifier 卡 todo** | 等待所有 worker done | 正常；若都已 done 仍 todo → `hermes kanban dispatch` |
| **Synthesizer 卡 todo** | verifier metadata.gate ≠ pass | 手动 `hermes kanban edit <verifier_id> --add-metadata '{"gate":"pass"}'` |
| **HTML 全部 0 字节 + Camoufox HTTP 500** | Meta VPN (28.0.0.x) 断连：DNS 解析到 28.0.0.x 假 IP，SSL_ERROR_SYSCALL。Step 0 curl 预检能提前发现 | 检查 `ip route get 8.8.8.8` 是否走 Meta；RSS 仍可用（feedparser 走不同路径）；继续 Step 4-5，Camoufox worker 等网络恢复后自动重试。详见 `references/meta-vpn-network-failure.md` |
| **Cron 用旧版 skill 跑完一整天（已实证 2026-06-10）** | 当天 cron 04:28 启动时 git pull 拉到旧代码；之后你 commit 了新代码（timeout 修复、HTML_SCRIPT_IDS 扩展），但 cron session 已经跑完 Step 1 不会再拉。结果：旧版 15s timeout → RSS 只拿 4 条（预期 27+）；旧版 12 HTML 脚本 → 少跑 6 站；旧版 9 Camoufox worker → 多跑了 6 个不需要的 worker。最终靠 Camoufox worker 弥补，报告没丢但效率差 | **规则：改完代码后必须确认下一次 cron 拉到新版本。** 方法：(1) 改完立即 `git push`；(2) 下次 cron 手动验证 `head -20 ~/.hermes/cron/output/ec5ea562d589/<latest>.md` 看 version 字段；(3) 重大改动考虑手动 `hermes cron run ec5ea562d589` 立即验证 |
| **feedparser/urllib SSL 超时（Meta VPN）** | VPN 下 TLS 握手 8-10s，旧 15s socket timeout 导致全部 RSS 站 0 条。Camoufox 不受影响（长连接复用） | `socket.setdefaulttimeout(30)` + terminal timeout=900。详见 `references/feedparser-vpn-timeout.md` |
| **站点分类错误** | scrape 脚本调 Camoufox REST API 但被放进 HTML_SCRIPT_IDS（如 boomkat, point_of_departure, wild_city） | grep `CAMOFOX_BASE`/`camoufox` 确认脚本实际依赖。详见 `references/site-classification-methodology.md` |
| **HTML 脚本 CLI 不兼容** | hear65/roots_world/world_music_central 不接受 `--days`（分别用 `--hours`/`--ref-date`/`--hours`），parallel scraper 传 `--days 1.5` → rc=2 直接失败 | 修脚本加 `--days` 支持，或 parallel scraper 对这些站特殊处理。详见 `references/html-script-cli-compat.md` |
| **mixmag_asia stdout 污染** | 脚本先 `print(json.dumps(...))` 再 `stderr.write(...)` 但部分版本把 status 写到 stdout，破坏 JSON 解析 | 确认 stderr vs stdout 分离；必要时用 `2>/dev/null` + 只重定向 stdout |
| **wild_city 不属于 HTML 层** | scrape_wild_city.py 依赖 `CAMOFOX_BASE = http://127.0.0.1:9377`，不是纯 HTTP 脚本 | 从 HTML_SCRIPT_IDS 移除，归入 Camoufox 组 |
| **RSS 实际耗时 300-700s** | 28 站 × 30s socket timeout = 840s 理论上限，VPN 慢站 20-28s/站累积 | terminal 必须 `timeout=900`，不能用 600 或 300 |
