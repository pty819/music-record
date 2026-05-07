---
name: music-daily-recs
description: 每日巡检 43 个音乐评论站，fan-out scraper 并行抓取，汇总评分后推送 GitHub + Telegram。前卫/实验/学院派爵士/电子/世界音乐定向采集。
category: music
tags: [music-reviews, avant-garde, experimental, jazz, electronic, world-music, kanban, fan-out]
author: hermes-agent
version: 1.0
created: 2026-05-07
updated: 2026-05-08
trigger_condition: 每天北京时间凌晨 03:00 cron 触发，或手动调用
---

# Music Daily Recs — Kanban Fan-Out Pipeline

## 架构

```
T0  orchestrator   cron/手动触发 → 读取 sites.json → 创建 43 个 scraper 任务
     ↓
[T1a ... T1z]  43 个 scraper 任务，全部 parallel（受 dispatcher 并发数控制）
     ↓ (全部 done)
T44  aggregator    收集所有 scraper 的输出 JSON，合并去重
     ↓
T45  filter        按评分公式打分，>= 6 全部保留
     ↓
T46  writer        生成 markdown → git push 到 github.com/pty819/music-record
     ↓
T47  notifier      推送 top 20 到 Telegram
```

## 站点配置

sites.json 在 `/home/liyifan/.minimax/music-sites/sites.json`（从 music-record repo 同步）

共 46 个站点，其中 43 个活跃 + 3 个 skip：
- **skip**（ Boomkat / Syrphe / Textura）：已知无法访问，跳过
- **RSS 优先组**（~21 站）：feedparser 直接解析
- **Playwright 组**（~22 站）：browser_navigate headless + stealth
- **搜索降级组**：paywall/cloudflare 站降级到 web_search

### ⚠️ Fluid Radio — 静态存档库

Fluid Radio 的 RSS feed 灌入的是 **2013–2022 年全部历史存档**（671 条），站点本身可能已停更，后续爬虫不会抓出新内容。

**处理方式**：sites.json 中 `crawl_strategy` 设为 `skip`。Aggregator **不**从 `fluid_radio_reviews.json` 选（太老），而是：
- 推荐生成时，额外从 `fluid_radio_reviews.json` **随机抽取 2–3 条**加入推荐池
- 抽取时优先选 `type: review`、标签匹配实验/声景/环境方向的条目
- 在 markdown 中标注来源为 `[Fluid Radio Archive]`，与当期新内容分开

### ⚠️ The Wire 特殊配置

The Wire 的专辑评论（Soundcheck）在印刷版magazine里，几乎全付费。但 `/audio/tracks` 里有大量免费音乐推荐内容（Wire mix、Premiere、Unlimited Editions、Invisible Jukebox 等），每个帖子内含 Tracklist，是优质的实验/前卫音乐来源。

`reviews_url` 应设为 `https://www.thewire.co.uk/audio`，`allowUrlPatterns` 设为 `["/audio/", "/tracks/", "/on-air/"]`。解析目标不是正文，而是 `Tracklist:` 标题后的段落，从中提取「艺人 — 曲名」或「艺人 — *专辑名*」格式的曲目列表作为推荐来源。

## 评分公式

```
total_score = critic_quality(0-5) + taste_match(0-5) + novelty(0-3)
             + cross_domain_bonus(0-3) + regional_bonus(0-2) - mainstream_penalty(0-3)
```

- **主推荐**：总分 >= 9，全写入 markdown
- **候选补充**：总分 6-8，全写入 markdown
- **不推荐**：总分 < 6，不写入（但记录在 JSON 备查）

## 评分细则

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

**跨子类叠加**：同时命中两个以上不同子类（例如 synthwave + darksynth，或 dungeon synth + dark ambient），额外 +1。

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
| 非纯 nostalgia 模仿，在叙事/世界观/音色设计有明显扩展 | 评论明确强调 | +1 |
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

**Synthwave / Retrowave / Dungeon Synth / Dark Ambient 降权规则（补充）**

- Synthwave / Retrowave：只有 80s nostalgia aesthetic，没有明显声音创新 → -1；更接近普通 pop/synthpop 单曲 → -1；评论只是 "fun", "nostalgic", "retro vibes" → -1；纯霓虹封面 + 常规鼓机 + 常规 lead synth → -1
- Dungeon Synth / Dark Ambient：只是低保真循环 pad 堆叠，没有明显叙事感/音色设计/世界构建 → -1；纯 tape-noise/lo-fi texture 但无细节支撑 → -1；更像 demo/sketch/scene ephemera → -1

## 推荐原因写法规范

✅ 把自由爵士管乐、粗粝电子纹理和近乎仪式性的打击循环缝在一起，张力非常足。
✅ 在南岛/东南亚打击乐语感上叠加氛围电子与现场采样，既有地景感也有现代制作感。
✅ 用 darksynth / horror-synth 的重型音色和明确的专辑结构把复古合成器语言推向更强的戏剧张力。
✅ 不是单纯的 lo-fi fantasy 氛围堆叠，而是有明确场景感、叙事感和声音层次的 dark ambient / dungeon synth 作品。
❌ 很好听。很值得一听。很前卫。口碑不错。

## Markdown 结构

**GitHub 仓库全量版**：包含所有候选条目（评分 >= 6），格式如下：

```markdown
今日专辑推荐清单（YYYY-MM-DD）
更新时间：HH:MM 北京时间
数据来源：X 个站 | Y 篇候选

## 主推荐（top 20，按评分排序）

1. **专辑名** — [艺人名](https://example.com)
   类型：`类型标签`
   推荐原因：一句具体的话
   来源：[站点名](https://site.com) | [文章标题](https://article.com)
   评分：N

## 候选补充（评分 6-8，全量写入）

1. **专辑名** — [艺人名](https://example.com)
   ...

## 今日全部候选（按评分排序）

| # | 专辑 | 艺人 | 来源 | 类型 | 评分 | 备注 |
|---|---|---|---|---|---|---|
| 1 | Album | Artist | Site | Type | 18 | 主推荐 |
...
```

**Telegram 推送版**：只取前 20 条主推荐（评分最高的 20 条），精简格式。

## 输出规范

**全部候选记录（强制执行）**：
- Markdown 必须包含所有经过评分的候选专辑（>= 6 分）
- 包含"今日全部候选"节，每行：`# | 专辑 | 艺人 | 来源 | 类型 | 评分 | 备注`
- 备注列：主推荐 / 候选补充 / 全文未获取 / 搜索补充 / 非当天首发 / 评分<6
- paywall 站且 cross-site 搜索无实质内容 → 标注"全文未获取"，不入主推荐/候选补充，但仍列全部候选表

**两套输出**：
- Telegram：top 20 主推荐，精简格式
- GitHub 仓库：全量 markdown + JSON

## 执行步骤

### Step 0 — 同步站点配置

从 GitHub 拉取最新的 sites.json：

```python
import subprocess
result = subprocess.run(
    ["git", "pull", "origin", "main"],
    cwd="/home/liyifan/.minimax/music-sites",
    capture_output=True, text=True
)
```

sites.json 路径：`/home/liyifan/.minimax/music-sites/sites.json`

### Step 1 — 创建 scraper 任务

读取 sites.json，遍历所有 `crawl_strategy != "skip"` 的站点，为每个创建 kanban 任务：

```python
import json, os

with open("/home/liyifan/.minimax/music-sites/sites.json") as f:
    data = json.load(f)

sites = [s for s in data["sites"] if s.get("crawl_strategy") != "skip"]

task_ids = []
for site in sites:
    t = kanban_create(
        title=f"scrape: {site['name']}",
        assignee="scraper",
        body=f"""抓取站点：{site['name']}
URL：{site.get('reviews_url') or site.get('homepage')}
RSS：{site.get('rss_url') or '无'}
策略：{'RSS' if site.get('has_rss') else 'Playwright headless'}
标签：{', '.join(site.get('tags', []))}

任务：
1. 如果有 RSS：用 curl + feedparser 解析最近 7 天条目
2. 如果无 RSS：用 browser_navigate headless 访问 reviews_url，提取文章列表
3. 对每篇评论：
   - 提取：专辑名、艺人、评分、评论URL、发布日期、来源
   - 跳转到详情页提取正文
   - 遇到 paywall/cloudflare：降级到 web_search 跨站搜索
4. 输出：JSON 数组，每条包含 {{album, artist, score, url, source, pub_date, tags, excerpt}}
5. 用 kanban_complete(summary=f"scraped N reviews from {site['name']}", metadata={{"site": site['id'], "count": N}})
""",
        workspace="dir:/home/liyifan/.minimax/music-sites/output",
        metadata={
            "site_id": site["id"],
            "site_name": site["name"],
            "has_rss": site.get("has_rss", False),
            "rss_url": site.get("rss_url"),
            "reviews_url": site.get("reviews_url") or site.get("homepage"),
            "tags": site.get("tags", []),
        },
    )
    task_ids.append(t["task_id"])
```

### Step 2 — 创建 aggregator 任务（依赖所有 scraper）

```python
aggregator_task = kanban_create(
    title="aggregate: all music reviews",
    assignee="scraper",
    body=f"""读取所有 {len(task_ids)} 个 scraper 任务的输出文件，合并去重。

输出文件路径格式：/home/liyifan/.minimax/music-sites/output/{{site_id}}_{{date}}.json

步骤：
1. 遍历所有输出文件
2. 解析 JSON 数组，合并到主列表
3. 按 (album, artist) 去重，保留评分最高的来源
4. **自动推断 `type` 字段**（区分 review 和 feature）：
   - `artist` 和 `album` 都有内容 → `type: "review"`
   - `artist` 有内容但 `album` 无内容 → `type: "feature"`
   - The Wire 的 tracklist 来源 → `type: "tracklist"`
5. 输出：/home/liyifan/.minimax/music-sites/output/aggregated_{{date}}.json
6. kanban_complete(summary=f"aggregated N unique reviews", metadata={{"total": N, "deduped": M, "type_breakdown": {{"review": R, "feature": F, "tracklist": T}}}})
""",
    parents=task_ids,
)
```

### Step 3 — 创建 filter 任务

```python
filter_task = kanban_create(
    title="filter: score and rank all reviews",
    assignee="scraper",
    body="""读取 aggregated JSON，按评分公司打分，输出 markdown。

输入：/home/liyifan/.minimax/music-sites/output/aggregated_{{date}}.json
输出：
  - /home/liyifan/.minimax/music-sites/output/filtered_{{date}}.json（所有 >= 6 分的条目）
  - /home/liyifan/.minimax/music-sites/output/markdown_{{date}}.md（全量 markdown）

评分公式见 skill 文档。
Markdown 格式见 skill 文档的"Markdown 结构"节。
kanban_complete(summary="filtered N reviews, M >= 6", metadata={"total": N, "passed": M})
""",
    parents=[aggregator_task],
)
```

### Step 4 — 创建 writer 任务

```python
writer_task = kanban_create(
    title="write: push to GitHub",
    assignee="writer",
    body=f"""将 markdown 文件推送到 GitHub。

步骤：
1. 读取 /home/liyifan/.minimax/music-sites/output/markdown_{{date}}.md
2. 确定输出路径：pty819/music-record 仓库的 2026/{{MM}}/{{YYYY-MM-DD}}.md
3. git add → git commit → git push
4. 输出：推送的文件的 GitHub URL
5. kanban_complete(summary="pushed to GitHub", metadata={{"url": "..."}})
""",
    parents=[filter_task],
)
```

### Step 5 — 完成 orchestrator 任务

```python
kanban_complete(
    summary=f"创建了 {len(sites)} 个 scraper 任务 + 3 个 pipeline 任务",
    metadata={
        "total_sites": len(sites),
        "scraper_tasks": len(task_ids),
        "pipeline_tasks": [aggregator_task, filter_task, writer_task],
    }
)
```

## ⚠️ 执行前检查清单

- [ ] sites.json 路径正确：`/home/liyifan/.minimax/music-sites/sites.json`
- [ ] 各站点 URL 可达
- [ ] 当前日期用于文件名和标题
- [ ] workspace 设为 `dir:/home/liyifan/.minimax/music-sites/output`（不是 scratch！）
- [ ] scraper profile 已配置 `.env` + `config.yaml`（否则 401 崩溃）

## ⚠️ scraper profile 必须独立配置

Dispatcher 用 `hermes -p scraper` 启动 worker，scraper profile 若缺少 `.env` 和 `config.yaml`，worker 会因 401 认证失败立即崩溃。

必须创建：
```
~/.hermes/profiles/scraper/.env        # 复制主 .env 的 MINIMAX_API_KEY
~/.hermes/profiles/scraper/config.yaml # 必须含 model.provider/minimax-cn
```

**注意**：`auth.json` 中**只能有 `minimax-cn` 这一个 provider**。如果有 `minimax`（api.minimax.io）和 `minimax-cn`（api.minimaxi.com）同时存在，任务可能随机/按配置选了错误的 provider，导致 401。检查：

```bash
cat ~/.hermes/profiles/scraper/auth.json
```

确保只有 `minimax-cn` 条目。

## ⚠️ 跑新批次前先清旧任务（重要！）

每次运行新批次前，kanban board 会残留上一轮甚至上上轮的 `◻ todo` scraper 任务（每次 43 个，历史积压可达 100+ 个）。这些废任务必须先清理：

```bash
# 查看积压
hermes kanban list | grep "◻" | grep "scrape:" | wc -l

# 归档所有 ◻ todo 状态的 scraper 任务
hermes kanban list | grep "◻" | grep "scrape:" | awk '{print $2}' | while read id; do
  hermes kanban archive "$id"
done

# aggregator 任务如果也是 ◻ 且 parent 已全部 done，也可以清
```

清完之后再用 batch 脚本创建新批次。

## ⚠️ Pipeline 跑完后维护

每一轮 scraper 跑完后，aggregator 会自动变为 `▶ ready`。但如果手动重跑了 batch 脚本，旧 aggregator 的 parent 指向已归档的任务 ID，会卡在 `◻ todo` 永远不动。

处理步骤：
1. 确认所有 scraper 都是 `✓ done`
2. 如果有大量 `◻` scraper → 先清：`hermes kanban archive <id>`
3. 检查 aggregator 状态：`hermes kanban list | grep aggregate`
4. 如果 aggregator 还是 `◻ todo` → `hermes kanban show <id>` 看 `parents` 字段是否指向已归档任务；是的话：`hermes kanban archive <old_agg_id>`，然后重建

## RSS 关键词过滤（高相关进入候选）

- experimental, avant-garde, avant garde, sound art
- free jazz, avant-jazz, spiritual jazz, creative music
- drone, ambient, electroacoustic, tape music
- world fusion, world music, folk, ritual, gamelan
- modern composition, new music, contemporary classical
- jazz-rock, jazz fusion, chamber jazz
- glitch, IDM, experimental electronic
- improvisation, improvised music
- gamelan, kulintang, gong, austronesian
- synthwave, retrowave, outrun, darksynth, cyberpunk synth, horror synth
- dungeon synth, dark ambient, fantasy synth, medieval ambient, ritual ambient
- neoclassical dark ambient, berlin school, kosmische
- soundtrack-inspired, cinematic synth, atmospheric synth
- analog synth-forward electronic, occult electronics, folk-horror electronics

## RSS 已知失败站

| 站点 | 错误类型 | 处理 |
|---|---|---|
| Resident Advisor | "unbound prefix" — XML namespace 冲突 | 跳过，记录日志 |
| Point of Departure | "undefined entity &rsquo;" | 跳过，记录日志 |
| The Squid's Ear | "not well-formed (invalid token)" | 跳过，记录日志 |

## GitHub 推送

使用系统 git config 的认证（已通过 `gh auth login` 配置）。

推送路径：`pty819/music-record` 仓库 → `2026/{MM}/{YYYY-MM-DD}.md`

## 重要教训（2026-05-08 实测）

### auth.json 双 provider 导致 401

`hermes-agent` 的 `minimax-cn` provider 调用 `api.minimaxi.com`，但 `auth.json` 同时注册了 `minimax`（`api.minimax.io`）。任务若选了错误的 provider，key 在该端点被拒，5 次重试后放弃。

**任何 scraper 任务崩溃，先查 `auth.json` 是否有多余 provider。**

### The Wire 无法绕过

- RSS 返回 HTML 而非 XML
- /category/reviews 返回 404
- 无 RSS，无公开内容
- 跨站搜索（web_search）也未找到有效评论

**结论：The Wire 标记 `status=paywalled`，不重试。**

### Aggregator 输出

今天实测（2026-05-08）：
- 原始记录：各站 JSON 共约 4000+ 条
- 去重后：3158 条（`aggregated.json`）
- 评分 ≥6：1668 条（`filtered.json`）
- 生成 `daily_recs.md`：187 行，推荐 29 条（≥8分）+ 值得关注 20 条（6-8分）+ Fluid Radio 档案 3 条
