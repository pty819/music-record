---
name: music-daily-recs
description: 每日巡检 48 个音乐评论站，kanban fan-out 并行抓取，聚合评分后推送 GitHub + Telegram
category: music
cron_job: ec5ea562d589（每天 04:00 北京时间自动运行）
author: hermes-agent
version: 5.1
license: MIT
created: 2026-05-07
updated: 2026-05-27
trigger_condition: cron 每天 04:00 触发，或手动 `hermes cronjob run 6fd93b4a4c4c`
metadata:
  hermes:
    tags: [music-reviews, kanban, fan-out, scraper, aggregator]
    related_skills: [kanban-worker, hermes-agent-skill-authoring]
---

## 架构

```
cron 触发（04:00）
Step 0  预检：Auth + DB 健康
  ↓
Step 1  同步：git pull → cp skill + script + sites.json
  ↓
Step 2  RSS 批量抓取 (fast-rss-scrape.py)
        ↓ JSON 已输出到数据目录，无需 kanban
        ↓
Step 3  HTML/curl 抓取 (12 个 scrape_*.py 并行)
        ↓ 各站独立 *_reviews.json
        ↓
Step 4  **合并 RSS + HTML → scraped_raw.json** (merge_scraped.py)
        ↓ 统一文件，URL 去重
        ↓
Step 5  创建 Camoufox 抓取任务 + **parent-gated aggregator**
        (kanban-batch-scrape.py --confirm)
         ↓ 21 个独立 scraper + 1 个 aggregator（parent=所有 scraper）
         ↓
┌─ kanban 调度器接手（cron session 可以安全退出）─────┐
│                                                      │
│  21 个 scraper 并行（max_workers=3）                 │
│  ↓ 全部 done 后 parent-gate 解锁                     │
│                                                      │
│  aggregator（kanban worker，自动触发）               │
│  Step 6  **合并 Camoufox → scraped_raw.json**       │
│          (merge_scraped.py)                          │
│  Step 7  **并发评分 + 中文总结** (process_reviews.py)│
│  Step 8  **生成推荐 markdown** (generate_report.py)  │
│  Step 9  **清理 .py + Git push**                     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

## 新架构核心变化

| 旧方式 | 新方式 |
|--------|--------|
| cron agent 轮询等 21 个 Camoufox 完成 | cron 创建任务后立即退出 |
| cron 超时，Step 7-10 无人执行 | aggregator kanban task 自动接手后四步 |
| 靠 sleep 60 循环轮询 | 靠 kanban parent-gate 精确触发 |
| cron 卡半小时，可能超时死 | cron 几秒完成，无需等待 |

## 何时执行

| 触发方式 | 说明 |
|---------|------|
| cron 自动 | 每天 04:00 北京时间，cron job `6fd93b4a4c4c` 触发 |
| 手动 | `hermes cronjob run 6fd93b4a4c4c` |
| 排障 | 发现当日推荐未送达时手动触发重跑 |

## 🔒 Harness Constraints（不可违反）

### 1. RSS 站点绝对不开浏览器
`has_rss: true` → 只走 feedparser。不要 `browser_navigate`、不要 Camoufox。

### 2. 禁止现场调试
不要写 Python 脚本测日期过滤逻辑。模板里的 cutoff 是正确的，信任模板。

### 3. 禁止交叉验证
RSS 已有数据 → 立即写 JSON → 结束。不要开浏览器对比数据"看是不是更完整"。

### 4. 所有路径必须硬编码绝对路径
不用 `expanduser("~")`、不用 `~/` 相对路径。统一用 `/home/liyifan/...`。

### 5. 禁止手动创建 kanban task
`kanban-batch-scrape.py --confirm` 是唯一创建途径。手动循环 `kanban_create` 会 OOM。

### 6. 所有抓取源必须输出同一数据 Schema（硬约束，不可偏离）
RSS（`fast-rss-scrape.py`）、HTML/curl（`scrape_*.py`）、Camoufox kanban worker 三者输出的 JSON 格式和字段**必须完全一致**。此约束在 `kanban-batch-scrape.py` 的 worker 输出模板层已强制实施。任何偏差均导致 pipeline 合并或评分异常。

**如果 worker 输出格式不符合此标准，即认为任务失败，必须重跑。** `merge_scraped.py` 不承担格式兼容职能——它只合并，不垫背。

外包装：`{"meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."}, "items": [...]}`

每项字段（按顺序）：
```
album, artist, score, url, source, pub_date,
tags, excerpt, body, site_id, crawl_status, type
```

### 7. `cleanup_old_tasks()` 必须走 CLI
读走 `hermes kanban list`，写走 `hermes kanban archive`。禁止直接 SQLite 连接。

---

## 执行步骤

### Step 0 — 预检

```bash
# DB 完整性
python3 -c "
import sqlite3
c = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
print('DB_INTEGRITY:' + c.execute('PRAGMA integrity_check').fetchone()[0])
c.close()
"
# 期望输出: DB_INTEGRITY:ok

# Auth 检查 — scraper profile 必须只有 minimax-cn
bash /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/check-scraper-auth.sh
cat /home/liyifan/.hermes/profiles/scraper/auth.json | grep minimax-cn | wc -l
# 期望: 1（已删掉 minimax 国际版条目）

# 关键预检: scraper profile gateway 必须运行（否则 kanban scheduler 无法 spawn worker）
hermes gateway status scraper 2>&1 | grep -c "running"
# 期望: 1（如果显示 stopped，先 `hermes gateway start scraper`）
# ⚠️ 注意: 如果 default gateway (PID) 已在运行相同 token，scraper gateway 无法独立启动。
#   此时 kanban dispatch 通过 default gateway 正常运作 — 只要 default gateway 是 running 状态，
#   调度器可以正常 spawn worker。跳过启动 scraper gateway，直接进入 dispatch。
```

### Step 1 — 同步（仅 cron/自动化运行需要）

> 交互式运行时跳过此步。当前会话中的 skill 和脚本永远是最新版。

```bash
cd /home/liyifan/music-record && git pull origin main

# 同步 SKILL.md（git 源 → skill 目录 → cron 加载用）
mkdir -p /home/liyifan/.hermes/skills/music/music-daily-recs
cp /home/liyifan/music-record/skills/music/music-daily-recs/SKILL.md \
   /home/liyifan/.hermes/skills/music/music-daily-recs/

# 同步 kanban-batch-scrape.py（git 源 → ~/.local/bin/ 执行用）
cp /home/liyifan/music-record/bin/kanban-batch-scrape.py \
   /home/liyifan/.local/bin/

# ⚠️ fast-rss-scrape.py 必须同步到 skill + ~/.local/bin/，否则 cron 使用 stale 副本产生旧格式输出
cp /home/liyifan/music-record/bin/fast-rss-scrape.py \
   /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/
cp /home/liyifan/music-record/bin/fast-rss-scrape.py \
   /home/liyifan/.local/bin/

# 同步 merge_scraped.py（合并 RSS + HTML 数据用）
cp /home/liyifan/music-record/bin/merge_scraped.py \
   /home/liyifan/.local/bin/

# 同步 process_reviews.py + generate_report.py（评分+生成推荐）
cp /home/liyifan/music-record/bin/process_reviews.py \
   /home/liyifan/.local/bin/
cp /home/liyifan/music-record/bin/generate_report.py \
   /home/liyifan/.local/bin/

mkdir -p /home/liyifan/.minimax/music-sites
cp /home/liyifan/music-record/data/sites.json /home/liyifan/.minimax/music-sites/ 2>/dev/null || true
```

### Step 2 — RSS 批量抓取（27 站，~60 秒）

**⚠️ feedparser 挂起保护**：某些 RSS feed（ProgArchives、The Wire、Rest Is Noise PH）被 Cloudflare 保护，`feedparser.parse()` 会无超时地挂起。运行前设 socket 超时：

```bash
mkdir -p /home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)
python3 -c "
import socket
socket.setdefaulttimeout(15)
import sys
sys.argv = ['fast-rss-scrape.py', '-o', '/home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)/rss_merged.json']
exec(open('/home/liyifan/.hermes/skills/music/music-daily-recs/scripts/fast-rss-scrape.py').read())
" 2>&1
```

超时的站会被 catch 为 0 条（容错，不影响其他站）。

✅ 输出：`rss_merged.json` — 包含 27 个 RSS 站最近 2 天的全部文章
无 kanban 任务、无 LLM、无浏览器。

### Step 3 — HTML/curl 并行抓取（12 站，~120 秒）

使用专用 Python 脚本抓取没有 RSS 但可直接 curl 的站（8 个 HTML 站 + 4 个混合站），全部并行运行。

**适用脚本列表**（位于 `music-record/bin/`）：
```
scrape_all_about_jazz   scrape_dark_entries    scrape_downbeat
scrape_free_jazz_blog   scrape_jazz_trail     scrape_mixmag_asia
scrape_musique_machine  scrape_resident_advisor  scrape_sea_of_tranquility
scrape_songlines        scrape_squids_ear     scrape_wild_city
```

```bash
DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"

SCRIPTS="scrape_songlines scrape_all_about_jazz scrape_resident_advisor \
         scrape_dark_entries scrape_free_jazz_blog scrape_jazz_trail \
         scrape_squids_ear scrape_downbeat scrape_mixmag_asia \
         scrape_musique_machine scrape_sea_of_tranquility scrape_wild_city"

for s in $SCRIPTS; do
  timeout 120 python3 /home/liyifan/music-record/bin/${s}.py --days 3 \
    > "$DATE_DIR/${s#scrape_}_reviews.json" 2>/dev/null &
done
wait

echo "✅ HTML/curl 抓取完成"
# 检查各站产出
for f in "$DATE_DIR"/*_reviews.json; do
  count=$(python3 -c "import json; d=json.load(open('$f')); print(len(d.get('items', d)) if isinstance(d, dict) else len(d) if isinstance(d, list) else '?')" 2>/dev/null || echo "0")
  [ "$count" != "0" ] && echo "  $(basename $f): $count 条"
done
```

✅ 输出：各站独立 `{site_id}_reviews.json` 文件，格式与 RSS 标准一致 `{meta, items}`。

### Step 4 — 合并 RSS + HTML 数据 → scraped_raw.json

将 Step 2 的 `rss_merged.json` 与 Step 3 的各 `*_reviews.json` 合并为一个统一文件，URL 去重（保留 RSS 版本），供 aggregator 一次性读取。

```bash
DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"
python3 /home/liyifan/.local/bin/merge_scraped.py \
  --date-dir "$(pwd)/$DATE_DIR" \
  -o scraped_raw.json 2>&1
```

✅ 输出：`scraped_raw.json` — `{meta: {total, merged_from, scraped_at}, items: [...]}`
此处 `merged_from` 记录各源文件及条数，用于审计。

### Step 5 — 创建 Camoufox 抓取任务 + aggregator

```bash
# 先用 dry run 预览（应显示 ~21 个 Camoufox 站，RSS 站已被过滤）
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py

# 确认无误后创建
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py --confirm
```

⚠️ `kanban-batch-scrape.py` 已自动过滤 `has_rss=true` 的站，只创建无 RSS 的 Camoufox 站任务。
同时会自动创建一个 **aggregator task**，其 `--parent` 绑定所有 scraper task ID。

**至此 cron session 的工作结束。** kanban 调度器接手后续：scraper 完成后 aggregator 自动解锁执行。

### 监控（可选 — 查进度不阻塞）

当需要查看 Camoufox 抓取进度时：

```bash
# 静态检查各状态的任务数量
hermes kanban list | grep "scrape:" | awk '{print $2}' | sort | uniq -c | sort -rn

# 查看 aggregator 状态（◻ todo = 还在等 scraper 完成）
hermes kanban list | grep "aggregate:"
```

### 进度停滞恢复

如果长时间 no progress（连续 3+ 分钟 done 数不变）：

1. 查 gateway 状态：`hermes gateway status`（如果 stopped，`hermes gateway run --replace`）
2. 手动 dispatch：`hermes kanban dispatch`
3. 强制完成无声退出的 scraper 任务（状态 running 但进程消失）：
   ```bash
   hermes kanban list | grep "running.*scrape:" | awk '{print $2}' | while read tid; do
     ps aux | grep "$tid" | grep -q . || hermes kanban complete "$tid"
   done
   ```

### 后四步（Step 6-9）— 由 aggregator kanban worker 自动执行

以上步骤创建完成后，cron session 即可安全退出。后续 **四步操作由 aggregator kanban worker 自动完成**，无需人工介入：

| 步骤 | 操作 | 脚本 |
|------|------|------|
| Step 6 | 合并所有数据 → `scraped_raw.json` | `merge_scraped.py` |
| Step 7 | 并发评分 + 中文总结 → `processed.json` | `process_reviews.py` |
| Step 8 | 生成推荐 markdown → `recommend/{DATE}.md` | `generate_report.py` |
| Step 9 | 清理 .py 文件 + git push | git commands |

aggregator 的 task body 包含这些步骤的完整指令，kanban worker 读到后按序执行。详见 `kanban-batch-scrape.py` 中 aggregator body 模板。

### 结果确认

聚合任务完成后，检查推荐文件是否生成：

```bash
ls -la /home/liyifan/music-record/recommend/$(date +%Y-%m-%d).md
```

GitHub 查看：https://github.com/pty819/music-record

Telegram 推送：读取 `recommend/{DATE}.md`，≤4000 字符发全文，否则精简版 + GitHub 链接。

---

# 快速替代方案 A：fast-rss-scrape.py（纯 RSS，无 kanban）

当只需要 RSS 站的数据时，可以用此脚本替代整个 kanban pipeline。**零 LLM、零浏览器、<2 分钟跑完。**

```bash
# 最近 2 天，输出到文件
python3 /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/fast-rss-scrape.py \
  --days 2 -o /tmp/rss_merged.json
```
# 输出包含 meta + reviews 数组，格式与 _reviews.json 完全兼容
```

**限制：** 只覆盖 `has_rss: true` 的站（目前 27 个）。artist/album 靠标题正则提取，不够精确时字段会退化。Camoufox-only 站（21 个）不在此脚本范围内。

**适用场景：**
- 快速巡检当天 RSS 站产出，不等 kanban
- 调试某站 RSS 是否正常
- 配合 `merge_scraped.py` 作为 process_reviews.py 的输入

### 脚本文件：`scripts/fast-rss-scrape.py`

保存于 skill 目录。如需独立使用，可拷贝到 `~/.local/bin/`：

```bash
cp /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/fast-rss-scrape.py \\\
   /home/liyifan/.local/bin/
```

---

# 快速替代方案 B：RSS + HTML 快速通道（跳过 Camoufox）

当不需要 Camoufox 源（21 个无 RSS 站），只需要 RSS 站 + curl 可抓的 HTML 站时，跳过 kanban 全流程，手动跑。

**适用场景：** 用户说"先跑 rss 和 html 的，camoufox 不用管"时执行此路径。

## 步骤

### ① RSS 批量抓取（带 socket 超时保护）

```bash
DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"
python3 -c "
import socket
socket.setdefaulttimeout(15)
import sys
sys.argv = ['fast-rss-scrape.py', '-o', '$DATE_DIR/rss_merged.json']
exec(open('/home/liyifan/.hermes/skills/music/music-daily-recs/scripts/fast-rss-scrape.py').read())
" 2>&1
```

### ② 并行跑 curl HTML 抓取脚本（8 个，每个 ~30-120s）

```bash
DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"
SCRIPTS="scrape_songlines scrape_all_about_jazz scrape_resident_advisor scrape_dark_entries scrape_free_jazz_blog scrape_jazz_trail scrape_squids_ear scrape_downbeat"
for s in $SCRIPTS; do
  timeout 120 python3 /home/liyifan/music-record/bin/${s}.py --days 3 > "$DATE_DIR/${s#scrape_}_reviews.json" 2>/dev/null &
done
wait
```

⚠️ 注意：scrape 脚本只输出 stdout，不支持 `-o` 参数。

### ③ 合并 RSS + HTML → scraped_raw.json

```bash
cd /home/liyifan/music-record
python3 bin/merge_scraped.py --date-dir "$(pwd)/$DATE_DIR" -o scraped_raw.json 2>&1
```

### ④ 并发评分 + 中文总结（process_reviews.py）

```bash
cd /home/liyifan/music-record
python3 bin/process_reviews.py \
  --date-dir "$(pwd)/$DATE_DIR" \
  -i scraped_raw.json \
  -o processed.json \
  --max-workers 3 2>&1
```

✅ 线程池并发，N 条 ≈ 1 条的时间。评分在 prompt 中由 LLM 直接打分。
输出 `processed.json`（含 `total_score` + `_cn_summary`）。

### ⑤ 生成推荐 markdown + 推送

```bash
cd /home/liyifan/music-record
python3 bin/generate_report.py \
  --date-dir "$(pwd)/$DATE_DIR" \
  -i processed.json \
  --date $(date +%Y-%m-%d) 2>&1

# 校验已生成
ls -la recommend/$(date +%Y-%m-%d).md

# git push
git add -A "$DATE_DIR" recommend/$(date +%Y-%m-%d).md bin/process_reviews.py bin/generate_report.py
git commit -m "music-recs: $(date +%Y-%m-%d) quick RSS+HTML run"
git push origin main 2>&1 || echo "⚠️ git push failed (TLS), manual retry later"
```

---

## Scraper 模板关键指令

以下约束已内置于 `kanban-batch-scrape.py` 的 scraper body 模板，对所有站点生效：

| 规则 | 说明 |
|------|------|
| 时间范围 | 只抓 3 天内文章，超期停止翻页 |
| RSS 优先 | 有 RSS 就走 feedparser，不走浏览器 |
| Cookie 墙 | navigate 后检查并点击 Accept/Agree |
| CDATA 全文 | RSS <description> 含全文时用 feedparser.summary 获取前 500 字 |
| 非音乐过滤 | 跳过含 (BLU-RAY)、(UHD)、(VOD)、(DVD) 的条目 |
| 特稿格式 | 非传统乐评 → type: feature，score: null |
| 空结果 | 3 天内无文章 → 输出 []，不要报错或重试 |
| Paywall/CF | → status: paywalled 或 blocked，返回 [] |

---

## 站点配置

配置文件：`/home/liyifan/.minimax/music-sites/sites.json`
共 48 个活跃站点。**27 个 RSS + 21 个 Camoufox**（7 个站已在 2026-05-25 从 Camoufox 提升为 RSS）

| 策略 | 数量 | 说明 |
|------|------|------|
| RSS (http_get) | **27** | feedparser 直接解析，2 天过滤，`fast-rss-scrape.py` 批量抓取 |
| Camoufox (playwright_headless) | **21** | Camoufox 反检测引擎，浏览前 2 页，走 kanban worker |
| skip | 3 | Syrphe / Textura / Fluid Radio（停更/不可访问） |
详情和站点列表见 `sites.json`。

### 各站特殊处理

| 站点 | 注意事项 |
|------|---------|
| The Wire | RSS 91 条含 CDATA 全文（5K-20K）。内容为特稿/访谈，output `type: feature`，score: null |
| All About Jazz | 详情页 Cloudflare 保护。列表页提取 metadata，excerpt 为空 |
| Resident Advisor | 详情页 Cloudflare 保护。列表页含内联简短 excerpt（20-50 字） |
| ProgArchives | 全站 Cloudflare JS 挑战，RSS `feeds.feedburner.com/Progarchives/newreleases` 也返回 403。Camoufox NSS 库版本不兼容。**目前完全不可爬取**，发现即 `blocked`，force-complete |
| Musique Machine | 电影/音乐混合。非音乐过滤规则覆盖 (BLU-RAY/UHD/VOD/DVD) |
| The Quietus | 有 paywall。Camoufox 下可抓取 `/columns/quietus-reviews/` |
| VAN Magazine | 原 Camoufox，2026-05-25 发现其 RSS `van-magazine.com/feed/` 可用，已升为 RSS |
| Igloo Magazine | 原 Camoufox，2026-05-25 发现其 RSS `igloomag.com/feed` 可用，已升为 RSS |
| Jazz Journal | 原 Camoufox，2026-05-25 发现其 RSS `jazzjournal.co.uk/feed/` 可用，已升为 RSS |
| The Classic Review | 原 Camoufox，2026-05-25 发现其 RSS `theclassicreview.com/feed/` 可用，已升为 RSS |
| Bandcamp Daily | 原 Camoufox，2026-05-25 发现其 RSS `daily.bandcamp.com/feed` 可用，已升为 RSS |
| Prog Mistress | 原 Camoufox，2026-05-25 发现其 RSS `progmistress.com/feed` 可用，已升为 RSS |
| The Rest Is Noise PH | 原 Camoufox，2026-05-25 发现其 RSS `therestisnoiseph.com/feed/` 可用，已升为 RSS |
| The Squid's Ear | 极度高产出站（一次可抓 100+ 条）→ 极易耗尽 kanban worker 的 90-iteration budget。发现 blocked 时检查原因：若是 "Iteration budget exhausted"，force-complete。批量中产出 103 条的数据已在 JSON 中，不需要重跑 |
| Fluid Radio | 停更，skip。存档 2013-2022 |

### Camoufox 站转 RSS（已验证可用）

以下 7 个站当前标记为 `crawl_strategy: playwright_headless`，但实际有可用的 RSS feed。建议在 `sites.json` 中加 `has_rss: true` + `rss_url`，并在 scraper body 模板注入 rss_url 避免浏览器：

| 站点 | RSS 地址 | 验证结果 |
|------|---------|---------|
| VAN Magazine | `https://van-magazine.com/feed/` | status=200, 10 entries |
| Jazz Journal | `https://jazzjournal.co.uk/feed/` | status=200, 10 entries |
| The Classic Review | `https://theclassicreview.com/feed/` | status=200, 10 entries |
| Igloo Magazine | `https://igloomag.com/feed` | status=200, 9 entries |
| Bandcamp Daily | `https://daily.bandcamp.com/feed` | status=200, 35 entries |
| Prog Mistress | `https://progmistress.com/feed` | status=301→200, 10 entries |
| The Rest Is Noise PH | `https://therestisnoiseph.com/feed` | status=301→200, 10 entries |

## 评分方式（v3 — LLM 直接打分）

`process_reviews.py` 不再使用本地硬编码公式。评分细则写在 MiniMax API 的 prompt 中，由 LLM 根据文章内容直接判断打分。

### 评分 prompt 中的 6 个维度

| 维度 | 影响 | 说明 |
|------|------|------|
| 口味匹配度（权重最高） | 1-10 | 实验/前卫/爵士/电子/世界/暗潮 → 高分；主流流行 → 低分 |
| 创新性和独特性 | 加减分 | 独特的艺术视角、实验性元素 → 加分；模式化作品 → 减分 |
| 跨领域融合 | 加分 | 多种类型融合（如爵士+电子、世界+实验）→ 加分 |
| 地区特色 | +1 ~ +2 | 非主流地区（东南亚、东欧、非洲等）+1；独特文化视角额外+1 |
| 主流降权 | -1 ~ -2 | 大型主流厂牌、纯商业发行 → 降权 |
| 评论质量修正 | -1 | 内容太短（<200 字符）或纯新闻稿 → -1 |

### LLM 输出格式

每条调用返回严格 JSON：
```json
{"total_score": <整数1-10>, "cn_summary": "<150-300字中文综述>"}
```

`generate_report.py` 读取 `processed.json`，按分数分档展示（🌟9-10 / ⭐7-8 / 👍5-6 / 🔹3-4 / 📋1-2），零 API 调用。

### 旧公式（v2，已废弃）

旧 `aggregate_reviews.py` 使用的本地公式 `critic_quality + taste_match + novelty + cross_domain_bonus + regional_bonus - mainstream_penalty - excerpt_penalty` 已不再使用。仅在回滚时需要参考旧 `kanban-batch-scrape.py` aggregator 模板。

---

## LLM 评分 + 中文总结（process_reviews.py）

`process_reviews.py` 使用 MiniMax M2.7 进行评分和中文总结。评分和总结在**同一次 API 调用**中完成，线程池并发处理。

### API 配置

通过 **Anthropic SDK** 调用 `api.minimaxi.com` 的 MiniMax M2.7 模型：

```python
import anthropic
client = anthropic.Anthropic(
    api_key=MINIMAX_CN_API_KEY,
    base_url="https://api.minimaxi.com/anthropic",
    timeout=120,  # ⚠️ 最小 120s，MiniMax 响应可能极慢
)
```

⚠️ 环境变量名是 `MINIMAX_CN_API_KEY`（不是 `MINIMAX_API_KEY`）。API key 从 `~/.hermes/.env` 读取。

### 重试逻辑

线程池 + 每条约 15-20s，3 次重试 + 指数退避：

```python
for attempt in range(3):
    try:
        message = client.messages.create(
            model="MiniMax-M2.7",
            max_tokens=30000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        break
    except Exception as e:
        if attempt < 2:
            time.sleep(2 ** attempt)
```

### ⚠️ ThinkingBlock 处理

MiniMax 通过 Anthropic 端点返回两个 block（thinking → text）。只取 `block.type == 'text'`：

```python
for block in message.content:
    if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
        text = block.text
        break
```

### ⚠️ JSON 解析策略（3 层 fallback）

LLM 不一定返回干净 JSON，使用三层解析：
1. 直接 `json.loads(text)`
2. 从 markdown code block 提取（```` ```json {…} ``` ````）
3. 正则提取 `{...total_score...}` 包裹

任一成功即停止，全部失败则标记为失败（`total_score: 0, _cn_summary: "（评分失败）"`）。

### ⚠️ 不要用关键词拼接做总结

兜底输出的是"低频嗡鸣与氛围纹理"这类无意义文案，用户明确拒绝。必须走 LLM API。

---

## 输出文件

| 文件 | 路径 | 说明 |
|------|------|------|
| recommend markdown | `recommend/{YYYY-MM-DD}.md` | 唯一 markdown 输出，供 Telegram 推送 |
| 合并原始数据 | `2026/{MM}/{YYYY-MM-DD}/scraped_raw.json` | RSS+HTML+Camoufox 统一合并文件 |
| 评分+总结数据 | `2026/{MM}/{YYYY-MM-DD}/processed.json` | 含 total_score + _cn_summary，按分排序 |
| scraper JSON | `2026/{MM}/{YYYY-MM-DD}/{site_id}_reviews.json` | 各站原始抓取输出 |
| RSS 注入分析 | `references/rss-url-injection.md` | Camoufox 站转 RSS 方案和已验证站点列表 |

**Telegram 推送**：手动发，读取 `recommend/{DATE}.md`，≤4000 字符发全文，否则发精简版 + GitHub 链接。

---

## 文件路径一览

| 用途 | 路径 |
|------|------|
| RSS 批量抓取脚本 | `/home/liyifan/music-record/bin/fast-rss-scrape.py` |
| HTML 抓取脚本（12 个） | `/home/liyifan/music-record/bin/scrape_*.py` |
| 合并脚本 | `/home/liyifan/music-record/bin/merge_scraped.py` |
| 评分+总结脚本 | `/home/liyifan/music-record/bin/process_reviews.py` |
| 报告生成脚本 | `/home/liyifan/music-record/bin/generate_report.py` |
| 站点配置 | `/home/liyifan/.minimax/music-sites/sites.json` |
| batch 脚本 | `/home/liyifan/music-record/bin/kanban-batch-scrape.py` |
| skill 本文 | `/home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md` |
| Camoufox 服务器 | `/home/liyifan/camofox-browser/camoufox_server.py` |
| GitHub repo | `https://github.com/pty819/music-record` |
| Cron job ID | `6fd93b4a4c4c` |
| Camoufox 服务 | `systemctl --user hermes-camoufox.service` |

---

## Common Pitfalls

| 症状 | 检查 | 处理 |
|------|------|------|
| Git push 失败 | `cd ~/music-record && git pull origin main` 解冲突 | resolve → push |
| Telegram 推送超时 | cron 状态为 ok 但 delivery failed | 手动 `send_message` 或 GitHub 查收 |
| **Aggregator 卡 todo** | `hermes kanban show <task_id> | grep parent` — 查看是否有未完成的 parent scraper | 正常行为：aggregator 等所有 parent scraper done 才触发。如所有 scraper 已完成但仍 todo，手动 `hermes kanban dispatch` 触发调度 |
| Cron 漏触发 | `last reboot` + `journalctl --user -u hermes-gateway` | `hermes cronjob run 6fd93b4a4c4c` |
| DB 损坏 | `PRAGMA integrity_check` | 用源 schema 重建空 kanban.db |
| Scraper 全 fail | 查 scraper profile auth.json 是否只有 minimax-cn | 删除 minimax 国际版条目 |
| Scraper 空结果 | 查该站 JSON 是 `[]` 还是 `{excerpt:""}` | 按 references/site-investigation-methodology.md 排查 |
| Scraper gateway stopped | `hermes gateway status scraper` -> stopped | `hermes gateway start scraper` -> `hermes kanban dispatch` |
| **Scraper gateway token 冲突** | `hermes gateway start scraper` 报 "token already in use" | default gateway (PID) 已运行相同 token；kanban dispatch 通过 default gateway 正常工作，跳过专用 scraper gateway |
| Tasks stuck "ready"（不转 running） | `hermes kanban dispatch --dry-run` 显示 0 spawn | 启动 scraper gateway, 然后 `hermes kanban dispatch` |
| **Camoufox 广泛无声退出（~23 站）** | task 状态 "running" 但 `ps aux` 无对应进程 | `hermes kanban complete <id>`。影响全部 ~23 个 Camoufox 站点，非个别站问题 |
| **低活跃日大量空结果** | 周末/节假日后多数站输出 `[]` | 正常现象。Camoufox 站 3 天窗口内无新文章 -> 空结果非错误。继续推进即可 |
| Songlines 挂起（Camoufox tab 过期） | `ps aux | grep songlines` 运行 >5 分钟无输出 | `hermes kanban complete <task_id>`（JSON 通常已存在） |
| Boomkat 无限重试 | 多次 retry 后仍然挂起 | `kill -9 <PID>` -> retry 通常更快通过 |
| Point of Departure 无声退出 | worker 进程消失，task 留 running | `hermes kanban complete <task_id>`（小站，3 天内很空） |
| **aggregator 未创建** | `--confirm` 后无 `aggregate:` 任务 | 已自动创建。如确实缺失，手动：`hermes kanban create "aggregate: \`date +%Y-%m-%d\` post-processing" --parent <scraper_ids> --assignee scraper --workspace "dir:/home/liyifan/music-record/..." --skill kanban-worker --body "..."` |
| **MiniMax rate limit** | `process_reviews.py` 5 并发触发 MiniMax Token Plan 429 错误 | 降并发到 3：`--max-workers 3`；如仍 429 降到 2：`--max-workers 2` |
| **数据目录混入 *.py 调试脚本** | `git status` 显示 `.py` 文件被追踪（一次可多达 60+ 个） | aggregator body 已包含自动清理；如手动执行，先 `rm -f 2026/{MM}/{DATE}/*.py` |
| **Iteration budget exhausted（90/90）** | scraper blocked, reason "Iteration budget exhausted" | force-complete。Squid's Ear 一次 103 条在 90 轮内可能写不完，数据通常已在 JSON 中 |
| **Camoufox 站实际有 RSS** | scraper 走浏览器慢/挂，但该站实际有可用 RSS | 验证 RSS 后用 `fast-rss-scrape.py` 替代。改 sites.json 加 `has_rss: true` + `rss_url`；参考 `references/camoufox-to-rss-promotion.md` |
| **Scraper body 缺 rss_url** | kanban worker 无法直接知道 RSS 地址，需自行发现 | 改 `kanban-batch-scrape.py:147` body 模板，加 `rss_url={site.get('rss_url','')}` |
| **RSS 快速巡检** | 不想等 kanban，只要 RSS 站数据 | 用 `scripts/fast-rss-scrape.py`，<2 分钟出 27 站合并结果 |
| **feedparser 挂起（ProgArchives/The Wire/Rest Is Noise）** | Step 2 `feedparser.parse()` 无限等待，阻塞全脚本 | 运行前设 `socket.setdefaulttimeout(15)`，用 exec() 包装脚本（见 Step 2 示例） |
| **Scraper 脚本不支持 `-o` 参数** | 所有 12 个 scrape_*.py 只输出 stdout，不能写文件 | 重定向 stdout：`python3 bin/scrape_xxx.py --days 3 > output.json` |
| **MiniMax 批处理耗时（旧流程）** | 旧 `aggregate_reviews.py` 串行跑 MiniMax，42 条 ~13 分钟 | **已解决**：`process_reviews.py` 线程池 5 并发，42 条 ≈ 15-20 秒 |
| **Worker 输出格式不一致** | `kanban-batch-scrape.py` 模板曾输出裸 JSON 数组（缺 `body`、无 `{meta,items}` 包装），与 RSS/HTML 标准不符 | **✅ 已修复**：模板已改为 `{meta, items}` + 含 `body` 字段。下次 Camoufox 抓取起效。参见约束 #6 |
| **Aggregator 不读 rss_merged.json（旧流程）** | 旧 `aggregate_reviews.py` 不读 rss_merged.json，只 glob `*_reviews.json` | **旧流程遗留** — 新流程用 `merge_scraped.py` 合并后再处理，不依赖个别文件名 |
| **Aggregator 不兼容 dict 格式（旧流程）** | 旧 `aggregate_reviews.py` 只认 `isinstance(data, list)` | **旧流程遗留** — `merge_scraped.py` 统一处理 dict/array 两种格式 |
| RSS items 缺 _site 字段（旧流程） | 旧 aggregate_reviews.py 评分用 r.get("_site")，RSS 条目只有 site_id | **旧流程遗留** — 新 process_reviews.py 不依赖 _site 字段，LLM 直接按内容评分 |
| **Cron session 0 条消息** | cron 启动后 agent 未输出任何内容。可能 cron prompt 与 skill 步骤不一致、gateway 异常、或 prompt 中的路径/命令错误 | `hermes cronjob run <id>` 手动触发；检查 cron prompt 是否仍引用旧 skill 步骤 |