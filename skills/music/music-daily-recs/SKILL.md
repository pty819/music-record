---
name: music-daily-recs
description: 每日巡检 48 个音乐评论站，kanban fan-out 并行抓取，聚合评分后推送 GitHub + Telegram
category: music
cron_job: 6fd93b4a4c4c（每天 04:00 北京时间自动运行）
tags: [music-reviews, kanban, fan-out]
author: hermes-agent
version: 4.0
created: 2026-05-07
updated: 2026-05-22
trigger_condition: cron 每天 04:00 触发，或手动 `hermes cronjob run 6fd93b4a4c4c`
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
Step 2  kanban-batch-scrape.py --confirm
         （脚本创建 48 scraper 任务，2 并行 parent-gated）
  ↓（全部 done）
Aggregator  合并去重 → 评分 → LLM 中文总结 → recommend/{DATE}.md → git push → Telegram 推送
```

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
```

### Step 1 — 同步

```bash
cd /home/liyifan/music-record && git pull origin main

mkdir -p /home/liyifan/.hermes/skills/music/music-daily-recs
cp /home/liyifan/music-record/skills/music/music-daily-recs/SKILL.md \
   /home/liyifan/.hermes/skills/music/music-daily-recs/

cp /home/liyifan/music-record/bin/kanban-batch-scrape.py \
   /home/liyifan/.local/bin/

mkdir -p /home/liyifan/.minimax/music-sites
cp /home/liyifan/music-record/data/sites.json /home/liyifan/.minimax/music-sites/ 2>/dev/null || true
```

### Step 2 — 创建 scraper 任务

```bash
# 先用 dry run 预览
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py

# 确认无误后创建（脚本内部自动 cleanup 旧任务，创建 48+1 个）
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py --confirm
```

⚠️ 禁止手动循环 `kanban_create`。48 个无 parent 的 scraper 同时 spawn 会 OOM。

### Step 3 — 监控进度

```bash
python3 -c "
import sqlite3
c = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
for row in c.execute(\"SELECT status, COUNT(*) FROM tasks WHERE title LIKE 'scrape:%' GROUP BY status\").fetchall():
    print(f'{row[0]:>10}: {row[1]}')
c.close()
"
```

备选（CLI）：
```bash
hermes kanban list | grep -c "✓.*done.*scraper"   # 已完成数
hermes kanban list | grep "running" | grep scraper  # 当前运行中
```

### Step 4 — Pipeline 收尾

全部 scraper done 后，aggregator 自动运行。确认状态：

```bash
hermes kanban list | grep "aggregat"
# 期望: ✓ done
```

如果 aggregator 卡在 ◻ todo 超过 10 分钟：
```bash
# 手动 fallback
cd /home/liyifan/music-record
python3 bin/aggregate_reviews.py \
  --date-dir 2026/$(date +%m)/$(date +%Y-%m-%d) \
  --date $(date +%Y-%m-%d)
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
共 48 个活跃站点：

| 策略 | 数量 | 说明 |
|------|------|------|
| RSS (http_get) | ~22 | feedparser 直接解析，3 天过滤 |
| Camoufox (playwright_headless) | ~23 | Camoufox 反检测引擎，浏览前 2 页 |
| skip | 3 | Syrphe / Textura / Fluid Radio（停更/不可访问） |

### 暗潮方向（2026-05-20 新增，5 站）

| site_id | 名称 | 策略 | 备注 |
|---------|------|------|------|
| side_line | Side-Line | RSS | https://www.side-line.com/feed/ |
| post_punk_com | Post-Punk.com | RSS | https://www.post-punk.com/feed/ |
| i_die_you_die | I Die: You Die | RSS | https://www.idieyoudie.com/feed/ |
| peek_a_boo_magazine | Peek-A-Boo Magazine | RSS | http://www.peek-a-boo-magazine.be/all.rss |
| dark_entries_be | Dark Entries | Camoufox | 荷兰语站，无 RSS |

### 各站特殊处理

| 站点 | 注意事项 |
|------|---------|
| The Wire | RSS 91 条含 CDATA 全文（5K-20K）。内容为特稿/访谈，output `type: feature`，score: null |
| All About Jazz | 详情页 Cloudflare 保护。列表页提取 metadata，excerpt 为空 |
| Resident Advisor | 详情页 Cloudflare 保护。列表页含内联简短 excerpt（20-50 字） |
| ProgArchives | 全站 Cloudflare JS 挑战。走 RSS（feeds.feedburner.com/Progarchives/newreleases） |
| Musique Machine | 电影/音乐混合。非音乐过滤规则覆盖 (BLU-RAY/UHD/VOD/DVD) |
| The Quietus | 有 paywall。Camoufox 下可抓取 `/columns/quietus-reviews/` |
| Boomkat | 原 ASN 封锁，Camoufox fingerprint 可过 ✅ |
| Fluid Radio | 停更，skip。存档 2013-2022 |

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

aggregator 通过 **Anthropic SDK** 调用 `api.minimaxi.com` 的 MiniMax M2.7 模型：

```python
import anthropic
client = anthropic.Anthropic(
    api_key=MINIMAX_CN_API_KEY,
    base_url="https://api.minimaxi.com/anthropic",
    timeout=60,
)
message = client.messages.create(
    model="MiniMax-M2.7",
    max_tokens=30000,
    temperature=0.7,
    messages=[{"role": "user", "content": prompt}]
)
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

## 常见故障速查

| 症状 | 检查 | 处理 |
|------|------|------|
| Git push 失败 | `cd ~/music-record && git pull origin main` 解冲突 | resolve → push |
| Telegram 推送超时 | cron 状态为 ok 但 delivery failed | 手动 `send_message` 或 GitHub 查收 |
| Aggregator 卡 todo | `hermes kanban show <id> \| grep parent` | 归档旧 aggregator，手动 `aggregate_reviews.py` |
| Cron 漏触发 | `last reboot` + `journalctl --user -u hermes-gateway` | `hermes cronjob run 6fd93b4a4c4c` |
| DB 损坏 | `PRAGMA integrity_check` | 用源 schema 重建空 kanban.db |
| Scraper 全 fail | 查 scraper profile auth.json 是否只有 minimax-cn | 删除 minimax 国际版条目 |
| Scraper 空结果 | 查该站 JSON 是 `[]` 还是 `{excerpt:""}` | 按 references/site-investigation-methodology.md 排查 |