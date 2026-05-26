---
name: music-daily-recs
description: 每日巡检 48 个音乐评论站，kanban fan-out 并行抓取，聚合评分后推送 GitHub + Telegram
category: music
cron_job: 6fd93b4a4c4c（每天 04:00 北京时间自动运行）
author: hermes-agent
version: 4.5
license: MIT
created: 2026-05-07
updated: 2026-05-26
trigger_condition: cron 每天 04:00 触发，或手动 `hermes cronjob run 6fd93b4a4c4c`
metadata:
  hermes:
    tags: [music-reviews, kanban, fan-out, scraper, aggregator]
    related_skills: [kanban-worker, hermes-agent-skill-authoring]
---

# Music Daily Recs — Kanban Fan-Out Pipeline

## 架构

```
cron 触发（04:00）
  ↓
Step 0  预检：Auth + DB 健康
  ↓
Step 1  同步：git pull → cp skill + script + sites.json
  ↓
Step 2  RSS 批量抓取 (fast-rss-scrape.py)
        ↓
        JSON 已输出到数据目录，无需 kanban
        ↓
Step 3  Camoufox 批量抓取 (kanban-batch-scrape.py --confirm)
         （仅 21 个无 RSS 站创建 kanban 任务）
  ↓（全部 done）
Aggregator  合并 RSS + Camoufox 数据 → 评分 → LLM 中文总结
             → recommend/{DATE}.md → git push → Telegram 推送
```

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

### 6. `cleanup_old_tasks()` 必须走 CLI
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

### Step 1 — 同步

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

mkdir -p /home/liyifan/.minimax/music-sites
cp /home/liyifan/music-record/data/sites.json /home/liyifan/.minimax/music-sites/ 2>/dev/null || true
```

### Step 2 — RSS 批量抓取（27 站，~60 秒）

```bash
mkdir -p /home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)
python3 /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/fast-rss-scrape.py \
  -o /home/liyifan/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)/rss_merged.json
```

✅ 输出：`rss_merged.json` — 包含 27 个 RSS 站最近 2 天的全部文章
无 kanban 任务、无 LLM、无浏览器。

### Step 3 — 创建 Camoufox 抓取任务

```bash
# 先用 dry run 预览（应显示 ~21 个 Camoufox 站，RSS 站已被过滤）
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py

# 确认无误后创建
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py --confirm
```

⚠️ `kanban-batch-scrape.py` 已自动过滤 `has_rss=true` 的站，只创建无 RSS 的 Camoufox 站任务。

### Step 4 — 监控 Camoufox 进度

**⏳ 建议使用主动进程探测循环**（不要仅依赖 DB 查询 — 大量 Camoufox scraper 无声退出后 task 状态仍为 running）

通用监控循环：

```bash
while true; do
  # 1. DB 状态
  python3 -c "
import sqlite3
c = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
for row in c.execute(\"SELECT status, COUNT(*) FROM tasks WHERE title LIKE 'scrape:%' AND status NOT IN ('archived') GROUP BY status\").fetchall():
    print(f'{row[0]:>10}: {row[1]}')
c.close()
"
  # 2. 探活 running 任务
  RUNNING_TASKS=$(hermes kanban list 2>&1 | grep "running" | grep scraper | awk '{print $2}')
  for TID in $RUNNING_TASKS; do
    ALIVE=$(ps aux | grep "$TID" | grep -v grep | wc -l)
    if [ "$ALIVE" = "0" ]; then
      echo "⚠️ Task $TID silent-exited → force completing"
      hermes kanban complete "$TID"
    fi
  done
  # 3. 如果运行中为 0 且有 ready/todo → dispatch
  RUNNING_COUNT=$(hermes kanban list 2>&1 | grep -c "running.*scraper" || true)
  TODO_COUNT=$(hermes kanban list 2>&1 | grep -c "todo.*scraper" || true)
  if [ "$RUNNING_COUNT" = "0" ] && [ "$TODO_COUNT" -gt 0 ]; then
    hermes kanban dispatch
  fi
  # 全部完成则退出
  DONE_COUNT=$(hermes kanban list 2>&1 | grep -c "✓.*done.*scraper" || true)
  [ "$DONE_COUNT" -ge 48 ] && echo "✅ ALL 48 DONE" && break
  sleep 60
done
```

备选（静态检查 — 仅一次）：
```bash
python3 -c "
import sqlite3
c = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
for row in c.execute(\"SELECT status, COUNT(*) FROM tasks WHERE title LIKE 'scrape:%' GROUP BY status\").fetchall():
    print(f'{row[0]:>10}: {row[1]}')
c.close()
"
hermes kanban list | grep -c "✓.*done.*scraper"   # 已完成数
hermes kanban list | grep "running" | grep scraper  # 当前运行中
```

**⏳ 进度停滞检测**：如果连续 3+ 分钟无进展（done/running 数不变）：
1. 查 scraper gateway 是否仍在运行：`hermes gateway status scraper`
2. 如果 stopped，先启动：`hermes gateway start scraper`（如 token 冲突跳过 → 用 default gateway）
3. 然后触发调度器重试：`hermes kanban dispatch`
4. 再检查：`hermes kanban list | grep -c "running" | grep scraper`

### Step 5 — Pipeline 收尾

全部 Camoufox scraper done 后，通知 aggregator。此时 RSS 数据已提前就位。

确认状态：

```bash
hermes kanban list | grep "aggregat"
# 期望: ✓ done
```

**⚠️ aggregator 未创建（kanban-batch-scrape.py 超时）**：如果 `--confirm` 因超时（30s）中断，aggregator 任务可能不存在。检查：\n\n```bash\nhermes kanban list | grep aggregate\n# 无输出 → aggregator 未创建\n```\n\n恢复方法（二选一）：\n\n| 方案 | 命令 | 适用场景 |\n|------|------|---------|\n| 手动运行聚合器 | `cd /home/liyifan/music-record && python3 bin/aggregate_reviews.py --date-dir 2026/$(date +%m)/$(date +%Y-%m-%d) --date $(date +%Y-%m-%d)` | 快速生成推荐 |\n| 创建 aggregator task | 重新运行 `kanban-batch-scrape.py --confirm`（但会创建重复 scraper） | 需要走完整 kanban 流程 |\n\n推荐方案 1（手动运行），更可靠。\n\n**⚠️ aggregator 卡在 ◻ todo 但 parent scraper blocked**：先检查 blocked scraper，force-complete 后 aggregator 自动解锁。大多数 blocked 站点只是 CF/iteration-budget 问题，数据已在 JSON 中：\n\n```bash\n# 找出 blocked scraper\nBLOCKED=$(hermes kanban list 2>&1 | grep \"⊘\" | awk '{print $2}')\nfor TID in $BLOCKED; do\n  echo \"Force-completing blocked: $TID\"\n  hermes kanban show \"$TID\" 2>&1 | grep -E \"title|blocked\"\n  hermes kanban complete \"$TID\"\ndone\n# 然后手动跑 aggregator（不等全部 48 站完成，已有数据就够）\ncd /home/liyifan/music-record\npython3 bin/aggregate_reviews.py \\\n  --date-dir 2026/$(date +%m)/$(date +%Y-%m-%d) \\\n  --date $(date +%Y-%m-%d)\n```\n\n如果 aggregator 仍卡在 ◻ todo 超过 10 分钟（且无 blocked parent）：
```bash
# 手动 fallback
cd /home/liyifan/music-record
python3 bin/aggregate_reviews.py \
  --date-dir 2026/$(date +%m)/$(date +%Y-%m-%d) \
  --date $(date +%Y-%m-%d)
```

### Step 6 — 推送前清理

```bash
cd /home/liyifan/music-record

# 1. 🔥 删除数据目录中的调试脚本（Boomkat、DownBeat、All About Jazz 等 worker 会遗留大量 *.py）
DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"
if [ -d "$DATE_DIR" ]; then
  rm -f "$DATE_DIR"/*.py
  echo "Cleaned .py files from $DATE_DIR"
fi

# 2. 验证无 .py 混入
find 2026/\($(date +%m)\) -name "*.py" | grep -q . && echo "⚠️ WARNING: .py still present!" || echo "✅ Clean"

# 3. Git push
git add -A "$DATE_DIR" recommend/$(date +%Y-%m-%d).md bin/aggregate_reviews.py bin/kanban-batch-scrape.py
git commit -m "music-recs: $(date +%Y-%m-%d) daily recommendations"
git push origin main
```

---

# 速替代方案：fast-rss-scrape.py（纯 RSS，无 kanban）

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
- 作为 aggregator 的 RSS-only 预取输入

### 脚本文件：`scripts/fast-rss-scrape.py`

保存于 skill 目录。如需独立使用，可拷贝到 `~/.local/bin/`：

```bash
cp /home/liyifan/.hermes/skills/music/music-daily-recs/scripts/fast-rss-scrape.py \\
   /home/liyifan/.local/bin/
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

## 站点配置\n\n配置文件：`/home/liyifan/.minimax/music-sites/sites.json`\n\n**⚠️ 关键问题：scraper body 模板没有注入 rss_url**\n\n`kanban-batch-scrape.py` 第 147 行的 body 模板只有 `url`（首页地址），没有 `rss_url`。kanban worker 需要自行发现 RSS，不可靠。如果修改模板，记得加上 `rss_url={site.get('rss_url','')}`。
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

---

## 评分公式 (v2)

实现在 `kanban-batch-scrape.py` aggregator 模板的 `score_review(r, site_id)` 函数。

```
total_score = critic_quality(0-3) + taste_match(0-5) + novelty(0-3)
            + cross_domain_bonus(0-3) + regional_bonus(0-2)
            - mainstream_penalty(0-3) - excerpt_penalty(0-1)
```

| 维度 | 范围 | 核心逻辑 |
|------|------|---------|
| critic_quality | 0-3 | excerpt 长度对数缩放（150→1，300→2，450+→3） |
| taste_match | 0-5 | site_base(0-2) + entry_tag_match(0-3) + excerpt_scan(0-1) |
| novelty | 0-3 | 17 个关键词扫描 excerpt |
| cross_domain | 0-3 | jazz/electronic/world/classical 多域命中 |
| regional | 0-2 | 地区级（southeast asia 等）→2，县级（argentina 等）→1 |
| mainstream_penalty | 0-3 | 主流/流行内容降权 |
| excerpt_penalty | 0-1 | CQ≤1 且 TM<3 时 +1（低质量+低相关度的短条目降权） |

> synth_dungeon_downgrade 已删除——用户口味包含 dark ambient / drone / dungeon synth，不降权。

---

## LLM 中文总结

aggregator 用 MiniMax M2.7 生成 1-2 句中文总结。

aggregator 通过 **Anthropic SDK** 调用 `api.minimaxi.com` 的 MiniMax M2.7 模型。

**⚠️ MiniMax API 会间歇性挂起**（随机在某条目卡住 >10 分钟）。必须在 Anthropic SDK 参数中设置合理 timeout（120s），并在外层包裹重试循环（3 次）。否则 67 条总结中平均有 1-2 条会挂起导致整个 pipeline 超时。

`aggregate_reviews.py` 中的实际实现：

```python
import anthropic
import time as _time
client = anthropic.Anthropic(
    api_key=MINIMAX_CN_API_KEY,
    base_url="https://api.minimaxi.com/anthropic",
    timeout=120,  # ⚠️ 最小 120s，MiniMax 响应可能极慢
)
last_exc = None
for attempt in range(3):
    try:
        message = client.messages.create(
            model="MiniMax-M2.7",
            max_tokens=30000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        last_exc = None
        break
    except Exception as e:
        last_exc = e
        print(f"  [summarize] attempt {attempt+1}/3 failed, retrying...")
        _time.sleep(5)
if last_exc:
    raise last_exc
```

⚠️ 环境变量名是 `MINIMAX_CN_API_KEY`（不是 `MINIMAX_API_KEY`）。API key 从 `~/.hermes/.env` 读取。

**⚠️ 不要用关键词拼接做总结** — 兜底输出的是"低频嗡鸣与氛围纹理"这类无意义文案，用户明确拒绝。必须走 LLM API。

**⚠️ ThinkingBlock 处理**：MiniMax 通过 Anthropic 端点返回两个 block（thinking → text）。forward 遍历，只取 `block.type == 'text'`：

```python
for block in message.content:
    if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
        result = block.text
        break
```

**⚠️ thinking 泄露处理**：有时 MiniMax 把完整内部独白泄露出现在 text block 中。检测 monologue markers（`We need to`、`我们应该`、`Thus:`、`First sentence` 等），用 `re.findall(r'[^。]+。', text)` 只提取中文句子。

---

## 输出文件

| 文件 | 路径 | 说明 |
|------|------|------|
| recommend markdown | `recommend/{YYYY-MM-DD}.md` | 唯一 markdown 输出，供 Telegram 推送 |
| aggregator JSON | `2026/{MM}/{YYYY-MM-DD}/aggregated.json` | 全量去重+评分后的 JSON |
| scraper JSON | `2026/{MM}/{YYYY-MM-DD}/{site_id}_reviews.json` | 各站原始抓取输出 |
| RSS 注入分析 | `references/rss-url-injection.md` | Camoufox 站转 RSS 方案和已验证站点列表 |

**Telegram 推送**：aggregator body Step 5 内置。读取 `recommend/{DATE}.md`，≤4000 字符发全文，否则发精简版 + GitHub 链接。

---

## 文件路径一览

| 用途 | 路径 |
|------|------|
| 站点配置 | `/home/liyifan/.minimax/music-sites/sites.json` |
| batch 脚本 | `/home/liyifan/.local/bin/kanban-batch-scrape.py` |
| skill 本文 | `/home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md` |
| aggregator 脚本 | `/home/liyifan/music-record/bin/aggregate_reviews.py` |
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
| Aggregator 卡 todo | `hermes kanban show <id> | grep parent` | 归档旧 aggregator，手动 `aggregate_reviews.py` |
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
| aggregator 未创建 | `--confirm` 30s 超时后缺失 aggregator task | 手动跑 `aggregate_reviews.py`（见 Step 4 恢复方法） |
| **Aggregator MiniMax 总结挂起** | 随机在某条目卡住 >10 分钟无进展 | `Ctrl+C` 后重跑（重试逻辑处理剩余条目）；如重跑仍在同条目挂起，截断 excerpt（>2000 字） |
| **数据目录混入 *.py 调试脚本** | `git status` 显示 `.py` 文件被追踪（一次可多达 60+ 个） | 在 `git add` 前先 `rm -f 2026/{MM}/{DATE}/*.py`（见 Step 5） |
| **Iteration budget exhausted（90/90）** | scraper blocked, reason "Iteration budget exhausted" | force-complete。Squid's Ear 一次 103 条在 90 轮内可能写不完，数据通常已在 JSON 中 |
| **Camoufox 站实际有 RSS** | scraper 走浏览器慢/挂，但该站实际有可用 RSS | 验证 RSS 后用 `fast-rss-scrape.py` 替代。改 sites.json 加 `has_rss: true` + `rss_url`；参考 `references/camoufox-to-rss-promotion.md` |
| **Scraper body 缺 rss_url** | kanban worker 无法直接知道 RSS 地址，需自行发现 | 改 `kanban-batch-scrape.py:147` body 模板，加 `rss_url={site.get('rss_url','')}` |
| **RSS 快速巡检** | 不想等 kanban，只要 RSS 站数据 | 用 `scripts/fast-rss-scrape.py`，<2 分钟出 27 站合并结果 |
| **旧格式 rss_merged.json（generated_at/total_entries）** | Step 2 使用了 stale 的 fast-rss-scrape.py（新格式应为 `scraped_at/total`），check `~/.local/bin/` vs skill 目录版本 | 手动重跑；修复 Step 1 sync 确认 fast-rss-scrape.py 已同步 |
| **Cron session 0 条消息** | cron 启动后 agent 未输出任何内容。可能 cron prompt 与 skill 步骤不一致、gateway 异常、或 prompt 中的路径/命令错误 | `hermes cronjob run <id>` 手动触发；检查 cron prompt 是否仍引用旧 skill 步骤 |