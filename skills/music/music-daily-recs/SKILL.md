---
name: music-daily-recs
description: 每日巡检 43 个音乐评论站，fan-out scraper 并行抓取，汇总评分后推送 GitHub + Telegram。前卫/实验/学院派爵士/电子/世界音乐定向采集。
cron_job: 6fd93b4a4c4c（每天 04:00 北京时间自动运行 pipeline + git push）
category: music
tags: [music-reviews, avant-garde, experimental, jazz, electronic, world-music, kanban, fan-out]
author: hermes-agent
version: 1.9
created: 2026-05-07
updated: 2026-05-12
trigger_condition: 每天北京时间凌晨 04:00 cron 触发，或手动调用
---

# Music Daily Recs — Kanban Fan-Out Pipeline

## 架构（实际实现）

```
T0  orchestrator   cron agent = music-daily-recs skill 执行者
     ↓
Step 0  清理旧积压（归档 stale ◻ todo scraper） — 每次触发前必须
     ↓
Step 1  同步 sites.json（git pull）
     ↓
Step 2  python3 kanban-batch-scrape.py --confirm
     ↓（脚本内部：2并行 × 22批，parent-gated）
[T1a ... T1z]  43 个 scraper 任务
     ↓ (全部 done)
T44  aggregator    收集所有 scraper 的输出 JSON，合并去重，评分，写 markdown
     ↓ (aggregator 自身完成 git push)
Step 3  cron agent 推送 top 20 到 Telegram
```

**⚠️ 不要照着 Step 2 的代码示例手动创建任务** — 那段代码绕过了 batching，会导致 43 个 scraper 同时启动，OOM。正确做法是用 `kanban-batch-scrape.py`，它内部实现 2-at-a-time 的 parent-gated batching。

## Task Assignee 定义

| 任务 | assignee | 说明 |
|------|----------|------|
| 所有 scraper | `scraper` | 已配置的独立 profile，有独立 auth.json |
| aggregator | `scraper` | 同上，读取 scraper 的共享 workspace（即 music-record/2026/{MM}/{DD}/） |

## 站点配置

sites.json 在 `/home/liyifan/.minimax/music-sites/sites.json`（从 music-record repo 同步）
Output 写入 `~/music-record/2026/{MM}/{YYYY-MM-DD}/{YYYY-MM-DD}/`，即直接是 git 仓库路径

共 46 个站点，其中 43 个活跃 + 3 个 skip：
- **skip**（Boomkat / Syrphe / Textura）：已知无法访问，跳过。sites.json 中 `crawl_strategy: "skip"`
- **RSS 优先组**（~21 站）：feedparser 直接解析，**只取 7 天内条目**，超期停止翻页
- **Playwright 组**（~22 站）：browser_navigate headless + stealth，**只浏览列表页前 2 页**，筛选 7 天内文章，超期停止
- **搜索降级组**：paywall/cloudflare 站降级到 web_search，同样限制 7 天

### ⚠️ Fluid Radio — 静态存档库

Fluid Radio 的 RSS feed 灌入的是 **2013–2022 年全部历史存档**（671 条），站点本身可能已停更，后续爬虫不会抓出新内容。

**处理方式**：sites.json 中 `crawl_strategy: "skip"`。Aggregator **不**从 `fluid_radio_reviews.json` 常规参与评分，而是在推荐生成时额外从该文件**随机抽取 2–3 条**加入推荐池：
- 抽取时优先选 `type: review`、标签匹配实验/声景/环境方向的条目
- 在 markdown 中标注来源为 `[Fluid Radio Archive]`，与当期新内容分开

### ⚠️ The Wire — 已确认 paywalled

The Wire 的专辑评论（Soundcheck）在印刷版magazine里，几乎全付费。实测结果（2026-05-08）：
- `/category/reviews` 返回 404
- RSS（`https://www.thewire.co.uk/feed`）返回 HTML 而非 XML
- 跨站 web_search 未找到有效评论

**结论：sites.json 中 `status: "paywalled"`，不重试。**

### ⚠️ The Quietus — Playwright 可抓但有时崩溃

The Quietus 有 paywall，但 `browser_navigate` 访问 `/columns/quietus-reviews/` 后，cookie 过期前可以抓取部分正文。如果 scraper 任务因 CF/paywall 崩溃：先 `kanban unblock` 再 `kanban reclaim`，不要直接归档。

## 类型分类规则（`type` 字段）

scraper 输出 JSON 后，aggregator 需要自动推断 `type` 字段：

| type | 判断条件 | 是否参与推荐 |
|------|----------|-------------|
| `review` | `artist` 和 `album` 字段都有内容 | ✅ 参与评分 |
| `feature` | `album` 字段为空或为特辑标题（如 `"Spool's Out: ..."`、`"Reissue of the Week: ..."`），但 `artist` 有内容 | ✅ 参与评分（特辑常提及具体专辑），Markdown 输出时加 `▸ [FEATURE]` 前缀 |
| `tracklist` | 来源是 The Wire 的 tracklist 格式 | ✅ 参与评分，Markdown 输出时加 `▸ [TRACKLIST]` 前缀 |

**判断优先级**：先判断 tracklist（来源字段），再判断 review vs feature（album 字段是否为空/特辑格式）。

## 评分公式

```
total_score = critic_quality(0-5) + taste_match(0-5) + novelty(0-3)
             + cross_domain_bonus(0-3) + regional_bonus(0-2) - mainstream_penalty(0-3)
```

- **主推荐**：总分 >= 9，全写入 markdown，无上限
- **候选补充**：总分 6-8，全写入 markdown，无上限
- **不推荐**：总分 < 6，不写入 markdown（但记录在 JSON 备查）

### 评分细则

### critic_quality (0-5)
- 5：真正的乐评，正文具体提到编制/音色/结构/文化背景
- 4：有实质性评论，包含流派标签和描述
- 3：一般乐评，有基本信息
- 2：摘要短讯，无正文
- 1：只有标题和一句话
- 0：新闻稿/公告/票务

### taste_match (0-5)
- 5：同时命中多个口味维度（如 free jazz + electroacoustic + world fusion）
- 4：明确属于前卫/实验/avant-jazz/学院派电子等核心方向
- 3：相关但偏 adjacent
- 2：边缘相关
- 1：擦边球
- 0：完全不符合

**Synthwave / Darksynth / Dungeon Synth / Dark Ambient 追加加权（叠加到 taste_match 基础分）**

| 命中类型 | 关键词 | 追加加权 |
|---|---|---|
| synthwave 类 | synthwave, retrowave, outrun | +1 |
| darksynth 类 | darksynth, horror synth, cyberpunk synth | +2 |
| dungeon synth / fantasy 类 | dungeon synth, fantasy synth, medieval ambient | +2 |
| dark ambient 类 | dark ambient, ritual ambient, neoclassical dark ambient | +2 |
| cinematic / soundtrack 类 | soundtrack-inspired, cinematic synth, atmospheric synth | +1 |
| Berlin school / kosmische | berlin school, kosmische, kosmische musik | +1 |
| 跨子类叠加 | 同时命中两个以上不同子类 | 额外 +1 |

### novelty (0-3)
- 3：全新概念/跨文化方法/unusual instrumentation/地区首发
- 2：有明显创新元素
- 1：有新意但不突出
- 0：无新意

**Synthwave / Darksynth / Dungeon Synth / Dark Ambient 追加加权（叠加到 novelty 基础分）**

| 情况 | 条件 | 追加加权 |
|---|---|---|
| synth/darksynth + world/folk/ritual 元素结合 | 正文或标签明确提到 | +2 |
| dungeon synth + 现代 sound design / electroacoustic / field recording | 正文或标签明确提到 | +2 |
| 非纯 nostalgia 模仿 | 评论明确强调叙事/世界观/音色设计有明显扩展 | +1 |
| 评论强调 "textural", "cinematic", "worldbuilding", "ritualistic", "atmospheric" 且有细节支撑 | 非空话 | +1 |

### cross_domain_bonus (0-3)
- 3：横跨 3 个以上口味维度
- 2：横跨 2 个维度
- 1：跨 1 个维度
- 0：单一维度

**Synthwave / Darksynth / Dungeon Synth / Dark Ambient 追加交叉规则**

| 交叉组合 | 追加加权 |
|---|---|
| synthwave/darksynth + experimental electronic | +2 |
| darksynth + industrial / ritual / horror ambient | +2 |
| dungeon synth + dark ambient | +2 |
| dungeon synth + folk / medieval / world elements | +2 |
| dark ambient + electroacoustic / sound art | +2 |
| synth music + prog / fusion / jazz-rock | +2 |
| 同时横跨三类（例如 dark ambient + ritual electronics + world/folk） | 再 +1 |

### regional_bonus (0-2)
- 2：涉及东南亚/南岛/中亚/拉丁美洲/非洲等少见地区 scene
- 1：有地域特色但非核心
- 0：欧美主流

### mainstream_penalty (0-3)
- 3：纯流行、无实验性的 mainstream indie
- 2：有实验标签但内容空洞
- 1：偏主流但有可取之处
- 0：不属于 mainstream penalty 范围

**Synthwave / Retrowave / Dungeon Synth / Dark Ambient 降权规则**

- Synthwave / Retrowave：只有 80s nostalgia aesthetic，没有明显声音创新 → -1；更接近普通 pop/synthpop 单曲 → -1；评论只是 "fun", "nostalgic", "retro vibes" → -1；纯霓虹封面 + 常规鼓机 + 常规 lead synth → -1
- Dungeon Synth / Dark Ambient：只是低保真循环 pad 堆叠，没有明显叙事感/音色设计/世界构建 → -1；纯 tape-noise/lo-fi texture 但无细节支撑 → -1；更像 demo/sketch/scene ephemera → -1

## 推荐原因写法规范

✅ 把自由爵士管乐、粗粝电子纹理和近乎仪式性的打击循环缝在一起，张力非常足。
✅ 在南岛/东南亚打击乐语感上叠加氛围电子与现场采样，既有地景感也有现代制作感。
✅ 用 darksynth / horror-synth 的重型音色和明确的专辑结构把复古合成器语言推向更强的戏剧张力。
✅ 不是单纯的 lo-fi fantasy 氛围堆叠，而是有明确场景感、叙事感和声音层次的 dark ambient / dungeon synth 作品。
❌ 很好听。很值得一听。很前卫。口碑不错。

## 两套输出

- **GitHub 仓库**：全量 markdown（>= 6 分全部）+ JSON，路径 `2026/{MM}/{YYYY-MM-DD}/{YYYY-MM-DD}.md`
- **Telegram**：top 20 主推荐，精简格式，无全部候选表

## 执行步骤（cron job prompt 完整内容）

> **⚠️ 重要：这些步骤是 cron job `6fd93b4a4c4c` 的 `--prompt` 完整内容。每次触发都会原样执行。Step 0（积压清理）是**每次触发前必须执行的第一步**，不可跳过。**

以下步骤按顺序执行：

### ⚠️ Step 0 — 积压清理 + auth 检查（**每次 cron 触发必须首先执行**）

**自动化检查**（推荐）：
```bash
bash ~/.hermes/skills/music/music-daily-recs/scripts/check-scraper-auth.sh
```

**手动检查**：
```bash
# 1. 检查积压（旧 todo scraper 数量）
hermes kanban list | grep "◻" | grep "scrape:" | wc -l

# 2. 清理旧 todo scraper（只保留 done/running/blocked）
hermes kanban list | grep "◻" | grep "scrape:" | awk '{print $2}' | while read id; do
  hermes kanban archive "$id"
done

# 3. 确认 auth.json 只有 minimax-cn
cat ~/.hermes/profiles/scraper/auth.json
# 期望：credential_pool 里只有 "minimax-cn" 这一个 key，base_url 应为 https://api.minimaxi.com
# 如果同时有 "minimax"（api.minimax.io）→ 删除 minimax 条目，只留 minimax-cn

# 4. 确认 scraper profile config
cat ~/.hermes/profiles/scraper/config.yaml | grep -E "provider|model"
# 期望：provider: minimax-cn
```

### Step 1 — 同步站点配置

从 GitHub 拉取最新的 sites.json：

```bash
cd /home/liyifan/.minimax/music-sites && git pull origin main
```

sites.json 路径：`/home/liyifan/.minimax/music-sites/sites.json`
Output 路径：
- `~/music-record/2026/{MM}/{YYYY-MM-DD}/{YYYY-MM-DD}/` — 当天 scraper JSON + aggregated.json + filtered.json + markdown
- `~/music-record/recommend/{YYYY-MM-DD}.md` — top 20 推荐总结（精简版）
- 两个文件一起 commit + push

### Step 2 — 运行 batch 脚本（正确方式）

**⚠️ 不要手动创建任务。** 手动循环 `kanban_create` 会创建 43 个无 parent 的 task，dispatcher 会同时 spawn 43 个 scraper 进程，内存爆炸。

正确方式：

```bash
# dry run（预览会创建哪些任务）
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py

# 确认无误后，实际创建任务
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py --confirm
```

脚本内部逻辑：
1. 读取 sites.json，过滤 `crawl_strategy != "skip"` 的站点
2. 分批：每批 2 个 task，用 `parents=` 形成 parent-gated chain
3. batch 1 无 parent；batch 2 的 `parents=[t1a, t1b]`；batch 3 的 `parents=[t2a, t2b]`... 以此类推
4. 所有 43 个 scraper done 后，aggregator 自动 `▶ ready`
5. aggregator 的 `parents=` 填入全部 43 个 scraper task_id

**为什么 batch size = 2？** kanban dispatcher 对同一 profile 的并发 spawn 数有限制，加上 scraper 进程（每个带 headless 浏览器）内存峰值约 200-400MB，43 并发会直接 OOM。2 并行是经过测试的稳定值。

### Step 3 — 监控 scraper 进度

**⚠️ `--monitor` flag is broken** (always does a dry run). Use manual polling instead.

```bash
# 看 scraper 状态：done / running / todo 计数
hermes kanban list | grep -c "✓.*done.*scraper"    # 已完成
hermes kanban list | grep -c "◻.*scrape:"           # 仍待执行
hermes kanban list | grep "running" | grep scraper   # 当前运行中
```

**快速确认是否只有1个批次在跑（无重复/并行批次堆积）**：

```bash
# 查最近 scraper task_runs — 如果看到同一个 scraper 有多个 started_at 不同的 run，
# 且间隔在几分钟内 = 正常 retry（被 worker 超时踢出后 reclaim），不是并行批次
python3 - << 'EOF'
import sqlite3
from datetime import datetime
conn = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
cur = conn.cursor()
cur.execute("""
    SELECT tr.task_id, tr.status, tr.started_at, tr.ended_at, tr.outcome, t.title
    FROM task_runs tr JOIN tasks t ON t.id = tr.task_id
    WHERE t.title LIKE 'scrape:%'
    ORDER BY tr.started_at DESC LIMIT 10
""")
for r in cur.fetchall():
    s = datetime.fromtimestamp(r[2]).strftime('%H:%M') if r[2] else '?'
    e = datetime.fromtimestamp(r[3]).strftime('%H:%M') if r[3] else '?'
    print(f"{s}-{e} {r[4]:<12} {r[5][-30:]}")
conn.close()
EOF
```

这条命令可以快速排除「两个 cron 批次同时在跑」的误判 — parallel batches 不会出现，同一 scraper 的多个 run 永远是 sequential retry。
# 看某个 scraper 的详细输出
hermes kanban log <task_id> 2>&1 | tail -40

# aggregator 出现后检查它是否卡在 ◻ todo
hermes kanban list | grep "aggregat"
hermes kanban show <aggregator_id> | grep parents
```

### Step 4 — 等待 pipeline 完成

轮询直到 scraper 全部 done：

```bash
# 轮询直到完成（每 2-3 分钟一次）
sleep 120 && hermes kanban list | grep -c "✓.*done.*scraper" && hermes kanban list | grep "running" | grep scraper | wc -l
```

**⚠️ Dispatcher 卡死识别与恢复**：如果 `✓ done` 不再增加（计数器 plateau），但 `◻ todo` 还有剩余，说明 dispatcher 卡死。

**症状判断**：
- `✓ done` 停在 N，剩余 `(43 - N)` 个 `◻ todo`
- `running` 计数为 0（没有 scraper 在跑）
- 但 scraper 的 JSON 文件已经写入了

**恢复步骤**（立刻执行，不要等）：
```bash
# 1. 确认哪些 scraper JSON 实际已写入（workspace 已切换到当天子文件夹）
find ~/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)/ -name "*_reviews.json" -mmin -600 | wc -l

# 2. 检查 aggregator 状态
hermes kanban list | grep aggregat

# 3. aggregator 如果是 ◻ todo 且有父母已 done → 手动 dispatch
hermes kanban show <aggregator_id>  # 确认 parents 指向的是 done 的任务
hermes kanban dispatch <aggregator_id>  # ⚠️ 这个命令语法不对，见下方正确方式

# 正确方式：aggregator 不 dispatch 自己，需要 claim 然后它自己运行
# 但如果 dispatcher 卡死，aggregator 永远不会被捡起 → 用 fallback 聚合
```

**Fallback 聚合（aggregator 卡死时执行）**：
```bash
cd ~/music-record && python3 - << 'PYEOF'
import json, os, glob
from datetime import date

today = "2026-05-11"  # 替换为实际日期
date_dir = f"2026/{today[5:7]}/{today}"   # e.g. 2026/05/2026-05-11
files = glob.glob(f"{date_dir}/*_reviews.json")
# 只取当天子文件夹的 JSON
files = [f for f in files if os.path.getmtime(f) > 1700000000]

entries = []
for f in files:
    site = os.path.basename(f).replace("_reviews.json", "")
    try:
        with open(f) as fh:
            data = json.load(fh)
        if isinstance(data, list):
            for item in data:
                item["_site"] = site
                entries.append(item)
        elif isinstance(data, dict) and "reviews" in data:
            for item in data["reviews"]:
                item["_site"] = site
                entries.append(item)
    except: pass

# Dedupe by album+artist
seen = {}
for e in entries:
    album = (e.get("album") or "").strip().lower()
    artist = (e.get("artist") or "").strip().lower()
    key = (album, artist)
    score = e.get("score")
    if key not in seen:
        seen[key] = (e, score)
    else:
        old_score = seen[key][1]
        if score is not None and (old_score is None or score > old_score):
            seen[key] = (e, score)

deduped = [v[0] for v in seen.values()]
scored = [e for e in deduped if isinstance(e.get("score"), (int, float))]

print(f"Total: {len(entries)}, Unique: {len(deduped)}, Scored: {len(scored)}")

os.makedirs(date_dir, exist_ok=True)
with open(f"{date_dir}/{today}.md", "w") as f:
    f.write(f"# Daily Music Recommendations — {today}\n\n...")
with open(f"{date_dir}/aggregated.json", "w") as f:
    json.dump(deduped, f, ensure_ascii=False, indent=2)
PYEOF
```

然后手动 git push：
```bash
cd ~/music-record
git add "2026/$(date +%m)/$(date +%Y-%m-%d)/" recommend/$(date +%Y-%m-%d).md
git commit -m "Daily: $(date +%Y-%m-%d) — fallback aggregation"
git push origin main
```

### Step 5 — Pipeline 跑完后检查

```bash
# 确认所有 scraper done（期望：43 done）
hermes kanban list | grep -c "✓.*done.*scraper"

# 确认 aggregator done（期望：1 done）
hermes kanban list | grep "aggregat" | grep done

# 检查是否有孤儿 aggregator（旧的卡在 ◻ todo）
hermes kanban list | grep "◻" | grep "aggregat"
```

### ⚠️ kanban-batch-scrape.py 崩溃导致 scraper 任务孤立

**现象**（2026-05-12 实测）：脚本在第 144 行因 `NameError: name 'MM' is not defined` 崩溃。`{MM}` 模板变量名错误，实际变量名为 `MONTH`。**当前脚本已修复此 bug。**

**崩溃后的级联故障**：
1. 崩溃发生在 aggregator 创建之前
2. 已创建的 42 个 scraper task 变成孤立任务（无 parent-gating）
3. dispatcher 立即同时 spawn 所有 42 个 scraper → 内存爆炸
4. 40 个 scraper 落入 `◻ todo`（因 dispatcher 已满载，新 task 等待），剩余 2 个继续运行
5. 下次 batch 运行时，这 40 个 stale `◻ todo` 会被同时唤醒，再次并发

**症状识别**：
```bash
# 看到 ~40 个 scraper 同时 running，或 OOM
hermes kanban list | grep "running" | grep scraper | wc -l   # 期望 <= 2

# workspace 出现多个不同日期的 scraper JSON
ls ~/music-record/2026/*/2026-*/ *_reviews.json | head -20
```

**临时修复**：
```bash
# 清理所有 stale scraper todo（每次 batch 脚本运行前必须执行）
hermes kanban list | grep "◻" | grep "scrape:" | awk '{print $2}' | while read id; do
  hermes kanban archive "$id"
done
```

**Aggregator parent chain 断裂**（batch 脚本崩溃后的二次故障）：
- 如果 batch 脚本在 scraper 运行期间崩溃，aggregator 可能尚未创建
- 如果 aggregator 已创建但 scraper 全部 done，aggregator 的 `parents=` 已填入
- 但下一次 `kanban-batch-scrape.py --confirm` 会创建新的 aggregator（带新的 parent ID）
- 旧的 aggregator 仍有旧的 parent ID（指向已 archived 的 scraper），永远卡在 `◻ todo`

**症状**：
```bash
# 两个 aggregator 存在，一个 done，一个永远 ◻ todo
hermes kanban list | grep aggregat
```

**处理**：归档旧的失效 aggregator。

### ⚠️ Aggregator workspace 子目录陷阱

**现象**（2026-05-12 实测）：aggregator task 的 workspace 设为 `dir:/home/liyifan/music-record/2026/05/2026-05-12/`，scraper JSON 文件也在此目录，但 scraper agent 读取的是父目录（`2026/05/`）下的旧 aggregated.json。

**根因**：scraper agent 的行为是 `cd $HERMES_KANBAN_WORKSPACE`（进入目录），但 Hermes dispatcher 在执行时 agent 的 cwd 可能不是 workspace 路径。aggregator body 模板没有显式 `cd "$HERMES_KANBAN_WORKSPACE"`，导致 agent 在错误的 cwd 下运行。

**修复（verified 2026-05-12）**：aggregator body 中所有路径使用绝对路径，不用 `$HERMES_KANBAN_WORKSPACE`：

```python
# aggregator body 关键步骤
输入目录：{date_dir}  # 绝对路径，如 /home/liyifan/music-record/2026/05/2026-05-12
输入文件：{date_dir}/*_reviews.json

步骤：
1. cd {date_dir} && ls *_reviews.json  确认文件存在
2. 遍历 {date_dir}/*_reviews.json（绝对路径）
3. 输出到 {date_dir}/aggregated.json、{date_dir}/filtered.json、{date_dir}/{DATE}.md
4. recommend 文件写入绝对路径：/home/liyifan/music-record/recommend/{DATE}.md
```

**2026-05-12 实测结果**：195 total，24 filtered (≥6)，GitHub push 成功。

### ⚠️ Gateway 进程存活是 cron 触发的前提

APScheduler 运行在 gateway 进程内部。如果 gateway 崩溃退出或服务器重启，APScheduler 也会停止，导致 cron 漏触发。

**⚠️ Telegram 断线不会杀死 gateway** — 这是已被证伪的错误假设。Telegram 网络抖动、重连风暴不会导致 gateway 进程退出，gateway 有独立的重连机制。

**三种失效模式**

**① 服务器重启**（最常见）
- 整个机器重启 → gateway 进程自然消失
- 日志特征：`gateway.log` 有 `Received SIGTERM/SIGINT — initiating shutdown`（gateway 收到 SIGTERM 后主动退出），紧接着 `mcp-stderr.log` 出现大量 `===== [HH:MM:SS] starting MCP server` 重启条目
- 鉴别：`journalctl --user -u hermes-gateway` 可以看到 systemd 重启时间线
- 如果 gateway 在 04:00 之前因服务器重启而下线，且在 04:00 之后才重新上线 → cron 必然漏触发

**② APScheduler 独立崩溃**（次要，但隐蔽）
- gateway 进程本身存活（kanban dispatcher 继续运行），但 APScheduler 线程崩溃退出
- 日志特征：`agent.log` 中 `Scheduler started` 消失，`mcp-stderr.log` 无 gateway 重启记录
- 鉴别：`grep "Cron ticker" gateway.log` 在漏触发时段无输出，但 kanban dispatcher 日志仍在
- 可能触发条件：Telegram + Weixin 同时断连的重连风暴（04:00 时段）
- **2026-05-12 04:00 实测**：gateway 在线、kanban 正常运行，但 APScheduler 无日志 → scheduler 独立崩溃

**③ Gateway 进程 crash**（最严重）
- Telegram 网络不稳定 → gateway 进程频繁崩溃退出（crash loop）
- 每次退出在 `mcp-stderr.log` 有记录，但 `gateway.log` 无 `Cron ticker stopped` 日志
- `mcp-stderr.log` 中的 `===== [time] starting MCP server` 条目 = gateway 重启
- 如果发现 `===== [HH:MM:SS] starting MCP server 'MiniMax'` 在某段时间内大量重复重启 → gateway 在 crash loop 中

**诊断步骤**

```bash
# 1. 检查服务器是否重启过（第一时间查）
last reboot | head -5
uptime

# 2. 检查 systemd 重启时间线
journalctl --user -u hermes-gateway --no-pager 2>/dev/null | grep -E "Started|Stopped|restart" | tail -20

# 3. 检查 mcp-stderr.log — gateway 崩溃/重启记录
tail -100 ~/.hermes/logs/mcp-stderr.log | grep "starting MCP server"

# 4. 检查 APScheduler 是否正常运行
grep "Scheduler started\|apscheduler shut down" ~/.hermes/logs/agent.log | tail -10

# 5. 检查 cron ticker 状态（gateway 在线但 ticker 可能已死）
grep "Cron ticker" ~/.hermes/logs/gateway.log | tail -5

# 6. 确认 cron job 状态
hermes cronjob list | grep music-daily-recs
```

**补救触发**：发现 cron 漏触发后，立即手动触发：
```
hermes cronjob run 6fd93b4a4c4c
```
然后等待结果推送到 Telegram。如果 Telegram 不稳定导致 delivery timeout，job 状态仍为 ok，结果存档在 music-record GitHub。**但存档不等于替代推送**——必须确保 Telegram 收到结果。

**根本解法**：将 cron 调度器从 gateway 进程中独立出来（Hermes 未来的 `cron_mode: external`），避免 gateway crash 导致 cron 漏触发。

### ⚠️ 已知 Bug：aggregator parent-gating 偶尔失效

**现象**：所有 scraper ✓ done，但 aggregator 仍显示 ◻ todo，不自动 dispatch。

**根因**：`kanban-batch-scrape.py` 创建 aggregator 时填入的 parent task ID 列表可能指向了旧的/已归档的任务（跨 run 残留）。dispatcher 看到 parent 未完成，就不 dispatch aggregator。

**判断**：
```bash
hermes kanban show <aggregator_id> | grep parent
# 如果 parent IDs 全部是 archived/✓ done 状态但仍卡 ◻ todo → bug 触发
```

**处理**：归档旧 aggregator，手动 fallback 聚合。

**Telegram 推送**也是跟着 aggregator 一起跳过的。如果走了 fallback，Telegram 也不会发。下次改进：把 Telegram 发送做成独立 task，不要绑定在 aggregator body 里面。

### ⚠️ 推荐结果 Songlines 系统性偏高 — 根因分析

**现象**（2026-05-11 实测）：
- `filtered.json` 1723 条中 Songlines 占 1513 条（88%）
- `recommend/Top20` 全部 20 条均来自 Songlines，全是 10.0 分

**两层根因**：

① **filtered.json 是历史全量，不是当日快照**
`aggregated.json` 跨多天累积（3158 条），`filtered.json` 每次聚合只合并不清理。Songlines 持续有输出，其他站经常空数组（被 block/无更新），历史数据不断叠加，导致 Songlines 占比越来越高。

② **Aggregator 评分公式对世界音乐系统性偏高**
Aggregator 不用站点原生评分（大部分站没有 `score` 字段），全靠 excerpt 推断：
- Songlines 是世界音乐专精媒体，excerpt 文本质量高、文化背景描述具体 → `critic_quality` 打分偏高
- Songlines 内容持续命中 taste_match（世界音乐/非洲/拉丁）→ 再叠加 regional_bonus
- 两者叠加 → Songlines 的 `total_score` 系统性高于其他站

**根本修复方向**：
- `filtered.json` 改为「当日快照」而非累积：每次聚合前清空旧的，只写当轮结果
- Aggregator 优先用站点原生 score（如有），fallback 才用公式推断
- 加入 source 多样性约束：Top 20 保证每站不超过 3 条

### ⚠️ 聚合逻辑不是独立脚本

**常见误区**：不要找 `aggregate-recommendations.py`，它不存在。

aggregator 的行为由 `~/.local/bin/kanban-batch-scrape.py` 第 134 行起的 `agg_body` 模板定义。每次运行 `kanban-batch-scrape.py --confirm` 都会用这个模板创建新的 aggregator task。

要修改聚合输出行为（输出路径、文件数量、git push 范围），编辑的是 `agg_body` 字符串，不是某个独立脚本。

**2026-05-08 实测：scraper 任务崩溃 5 次后放弃，根因是 auth.json 有两个 provider。**

`hermes-agent` 的 `minimax-cn` provider 调用 `api.minimaxi.com`，但 `auth.json` 同时注册了：
- `minimax` → `api.minimax.io`（国际版，key 在此端点被拒，返回 401）
- `minimax-cn` → `api.minimaxi.com`（国内版，key 正常）

任务随机/按配置选了错误的 `minimax`（国际版），5 次重试全部 401。

**修复**：编辑 `~/.hermes/profiles/scraper/auth.json`，删除 `minimax` 条目，只保留 `minimax-cn`。

**任何 scraper 任务突然崩溃，先查 auth.json。**

## Pipeline 跑完后维护

### 每次 cron 触发前必须清理

> **此步骤已内置于 cron job prompt 的 Step 0 中，每次触发时自动执行。** 以下为说明性内容，供手动排障参考。

`kanban-batch-scrape.py` 每次运行会**新建 43 个 task ID**，旧任务的 `◻ todo` 状态不会自动清理。3 轮后 board 上会有 120+ 个 stale task。

**每次 cron 触发前，orchestrator 必须先归档上一轮的 stale scraper：**

```bash
# 检查当前积压
hermes kanban list | grep "◻" | grep "scrape:" | wc -l

# 归档所有旧 ◻ todo scraper（done/running/blocked 的保留）
hermes kanban list | grep "◻" | grep "scrape:" | awk '{print $2}' | while read id; do
  hermes kanban archive "$id"
done
```

### 手动重跑 batch 后的 aggregator 修复

如果手动重跑了 batch 脚本，旧 aggregator 的 `parents=` 指向已归档的 scraper ID，会卡在 `◻ todo` 永远不动。

判断方法：
```bash
hermes kanban show <aggregator_id> | grep parents
# 如果 parent 都是 archived 状态 → aggregator 已失效
```

处理：
1. `hermes kanban archive <old_aggregator_id>`
2. 重建：`hermes kanban create "aggregate: all music reviews" --assignee scraper --parent <actual_done_scraper_ids...>`
3. 确认新的 aggregator 是 `▶ ready` 后才算完成

## GitHub 仓库结构（music-record repo）

**三个组成部分**（每次 Pipeline 必须同步更新）：

| 目录 | 内容 | 说明 |
|------|------|------|
| `skill/` | skill 最新副本 | `avant-garde-daily-recs.md` + `references/` |
| `2026/{MM}/{DD}/{YYYY-MM-DD}/` | 当天乐评原始数据 | 全部 >= 6 分乐评，cron job 自动 push |
| `recommend/YYYY-MM-DD.md` | 每日推荐总结 | top 20 精简版，随 `2026/` 一起 commit |

> ⚠️ **三部分必须一起更新**：skill 文档变更时、每天 Pipeline 完成后，三部分必须一起 push 到 GitHub。不可只更新其中某一部分。

**repo URL**：`https://github.com/pty819/music-record`

**用户查收习惯**：上午 10 点左右看 GitHub 查收完整报告，Telegram 只收精简推送。Pipeline 凌晨 04:00 跑完，十点前结果已就绪。

## GitHub 同步（每日必须）

Pipeline 完成后的 git push 和 skill 文件管理通过 `~/music-record/` 仓库进行。

### 仓库结构

```
~/music-record/
├── skill/avant-garde-daily-recs.md   ← hard link to ~/.hermes/skills/music/music-daily-recs/SKILL.md
├── 2026/{MM}/{DD}/{YYYY-MM-DD}/     ← 当天 scraper JSON + aggregated + filtered + markdown
└── recommend/{YYYY-MM-DD}.md          ← top 20 推荐总结（精简版）
```

> ⚠️ **三部分必须一起 push**：`skill/`、`2026/`、`recommend/` 三个目录每次必须同时 commit，不可只更新其中某一部分。

**Hard link 说明**：skill 文件在两个路径共享同一份物理内容（同一 inode），修改任意一个自动同步：

```bash
# 验证 hard link（Links: 2 = 正常）
stat ~/.hermes/skills/music/music-daily-recs/SKILL.md | grep Links
stat ~/music-record/skill/avant-garde-daily-recs.md | grep Links
```

如果 `git pull` 覆盖了 `avant-garde-daily-recs.md`，hard link 会断开。重新建立：

```bash
rm ~/music-record/skill/avant-garde-daily-recs.md
link ~/.hermes/skills/music/music-daily-recs/SKILL.md ~/music-record/skill/avant-garde-daily-recs.md
```

### Post-pipeline git push

Pipeline 完成后进入 repo push 即可（scraper 已直接写入 music-record，无需复制）：

```bash
cd ~/music-record
git add "2026/$(date +%m)/$(date +%Y-%m-%d)/aggregated.json" "2026/$(date +%m)/$(date +%Y-%m-%d)/filtered.json" "2026/$(date +%m)/$(date +%Y-%m-%d)/$(date +%Y-%m-%d).md" recommend/$(date +%Y-%m-%d).md skill/avant-garde-daily-recs.md
git commit -m "auto: $(date +%Y-%m-%d) daily recs" || exit 0
git push
```

这条命令已内置在 cron job `music-daily-recs`（ID: `6fd93b4a4c4c`）里，凌晨 04:00 自动执行。

**三部分一起 push**：`skill/`、`2026/`、`recommend/` 三个目录每次必须同时 commit，不可只更新其中某一部分。

## 参考文件

- `references/gateway-crash-diagnosis.md` — 05-12 cron 漏触发的根因诊断：gateway crash loop 导致 APScheduler 停止，mcp-stderr.log 重启时间线，诊断命令
- `references/aggregator-workspace-trap.md` — 2026-05-12 aggregator 读错目录的根因分析：workspace 子目录陷阱、aggregator 读到自己输出文件的路径问题、正确 aggregator body 模板
- `references/directory-migration-checklist.md` — 目录结构迁移时必查的 5 个文件 + grep 命令

## 注意事项

- **workspace 必须统一**：`dir:~/music-record/2026/{MM}/{YYYY-MM-DD}/`（当天子文件夹，不是 scratch！）。scraper 各写各的 `{site_id}_reviews.json`，aggregator 读目录里所有 `*_reviews.json`，scratch 目录互相不可见。
- **并发控制**：不是 43 并行，是 **2 并行 × 22 批**。每批 2 个 task，全部 done 之后下一批才解锁（parent-gating）。这是 kanban dispatcher 对 scraper profile 的并发限制 + 进程内存限制共同决定的。
- **关于空 `score` 字段**：The Quietus、A Closer Listen 等站不给数字评分，这是正常的，不影响推荐质量。评分公式完全基于 `excerpt` 内容判断，只要 scraper 把 `excerpt` 抓完整即可。

## 配套文档

**ebook 仓库**：`https://github.com/pty819/music-daily-recs-ebook`
**在线阅读**：`https://pty819.github.io/music-daily-recs-ebook/`

使用 Sphinx + sphinxcontrib.mermaid 构建的电子书，详细图解了 music-daily-recs 的全流程架构。GitHub Actions workflow 使用 `uv` 管理依赖，参考 `.github/workflows/build.yml`。

> ⚠️ **uv cache pitfall**：`setup-uv@v4` 的 `enable-cache: true` 默认查找 `uv.lock`，如果项目没有 `uv.lock` 会报错 `No file matched to [**/uv.lock]`。解决办法：`enable-cache: false` 或在项目根 touch uv.lock。

### GitHub Pages 部署配置（重要）

`build.yml` 必须包含 `upload-pages-artifact` + `deploy-pages` 两个 step 才会在 `gh-pages` 环境真正生效，缺一不可。仅有 `upload-artifact` 只能打包 artifact，不会部署。

参考配置：

```yaml
- name: Upload Pages artifact
  uses: actions/upload-pages-artifact@v3
  with:
    path: _build/html

- name: Deploy to GitHub Pages
  id: deployment
  uses: actions/deploy-pages@v4
```

同时需要在仓库设置中启用 GitHub Pages（Source 设为 GitHub Actions）：

```bash
gh api repos/{owner}/{repo}/pages --method POST \
  -f build_type=workflow \
  -f source[branch]=main \
  -f source[path]=/   # path 不需要，因为 _build/html 已经包含了所有文件
```

### Sphinx RST 文件编写规范

⚠️ **不要在 .rst 文件中手动编写章节编号（如 1.1、2.3）**。

`index.rst` 的 toctree 已设置 `numbered: true`，Sphinx 会自动生成章节编号。如果 .rst 文件正文中自己写了 `1.1`、`2.3` 这样的编号，会导致页面显示双重编号（自动的 + 手动的），非常难看。

正确做法：`index.rst` 负责 toctree 的 `numbered: true`，各章节 .rst 文件只写标题和内容，**不写章节号**。

示例（错误）：
```rst
1.1 Core Concepts
-----------------
```

示例（正确）：
```rst
核心概念
--------
```

- **GitHub 推送**：使用系统 git config 的认证（已通过 `gh auth login` 配置）。
