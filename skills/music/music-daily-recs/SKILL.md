---
name: music-daily-recs
description: 每日巡检 46 个音乐评论站，fan-out scraper 并行抓取，汇总评分后推送 GitHub + Telegram。前卫/实验/学院派爵士/电子/世界音乐定向采集。
cron_job: 6fd93b4a4c4c（每天 04:00 北京时间自动运行 pipeline + git push）
category: music
tags: [music-reviews, avant-garde, experimental, jazz, electronic, world-music, kanban, fan-out]
author: hermes-agent
version: 3.1
created: 2026-05-07
updated: 2026-05-19
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
Step 3  cron agent 推送完整推荐 markdown 到 Telegram
```

**⚠️ 不要照着 Step 2 的代码示例手动创建任务** — 那段代码绕过了 batching，会导致 43 个 scraper 同时启动，OOM。正确做法是用 `kanban-batch-scrape.py`，它内部实现 2-at-a-time 的 parent-gated batching。

## Task Assignee 定义

| 任务 | assignee | 说明 |
|------|----------|------|
| 所有 scraper | `scraper` | 已配置的独立 profile，有独立 auth.json |
| aggregator | `scraper` | 同上，读取 scraper 的共享 workspace（即 music-record/2026/{MM}/{YYYY-MM-DD}/） |

## 站点配置

sites.json 在 `/home/liyifan/.minimax/music-sites/sites.json`（从 music-record repo 同步）
Output 写入 `~/music-record/2026/{MM}/{YYYY-MM-DD}/`（当天子文件夹），即直接是 git 仓库路径

共 46 个站点，其中 43 个活跃 + 3 个 skip：
- **skip**（Syrphe / Textura / Fluid Radio）：已知无法访问或仅历史存档，跳过。sites.json 中 `crawl_strategy: "skip"`
- **Boomkat**：原 ASN 黑名单 skip，**2026-05-19 重新验证：Camoufox fingerprint 可绕过 Cloudflare ASN 封锁** ✅ 已恢复为 `playwright_headless`
- **RSS 优先组**（~21 站）：feedparser 直接解析，**只取 3 天内条目**，超期停止翻页
- **Camoufox 浏览器组**（~23 站，原 Playwright 组）：全量通过 Camoufox 反检测引擎驱动（详见下方配置段），browser_navigate 自动路由到 `localhost:9377` 的 Camoufox HTTP 服务器，非 vanilla Playwright。**只浏览列表页前 2 页**，筛选 3 天内文章，超期停止
- **搜索降级组**：paywall/cloudflare 站降级到 web_search，同样限制 3 天

**ⓘ 新 session 须知**：所有 `browser_navigate` / `browser_snapshot` / `browser_click` 调用自动通过 Camoufox 反检测引擎——由 `~/.hermes/config.yaml` 的 `browser.engine: auto` + `.env` 的 `CAMOFOX_URL` 路由，无需手动指定。Camoufox 服务器由 systemd 用户服务 `hermes-camoufox.service` 开机自启。

### Browser Configuration (Anti-blocking) — Python Camoufox Server + systemd

2026-05-19 重大更新：Camoufox 从 Node.js 包（`camoufox-js`）切换到 **Python 独立 HTTP 服务器 + 用户级 systemd 自启**。原 ARM64 上 `camoufox-js` 缺失原生模块不可用。新方案：

**架构**：`~/camofox-browser/camoufox_server.py`（Python REST 服务，端口 9377）通过 systemd 用户服务自启。Hermes 配置为通过 `CAMOFOX_URL` 连接。

**配置**：
```yaml
# ~/.hermes/config.yaml
browser:
  engine: auto
  camofox:
    url: http://localhost:9377
```
以及 `.env`：
```
CAMOFOX_URL=http://localhost:9377
```

**服务管理**：
```bash
systemctl --user enable hermes-camoufox.service   # 开机自启
systemctl --user start hermes-camoufox.service     # 手动启动
systemctl --user status hermes-camoufox.service    # 检查状态
```

Camoufox 提供比默认 Playwright 浏览器更好的 fingerprint stealth，显著提高对 Cloudflare 保护站点的抓取成功率。详见 `references/camoufox-configuration.md`。

**已知限制**：
- `browser_click` 通过 Camoufox 服务器时可能超时（30s timeout），可直接用 `browser_navigate` 替代
- `browser_console` JavaScript 评估不受支持

**2026-05-19 实测突破**：Camoufox Python 版成功绕过 **Boomkat** 的 Cloudflare ASN 黑名单（原标记 skip）。AAJ 和 RA 的详情页级 Cloudflare 保护仍不可绕过，但列表页可正常提取 metadata。

**当前 Cloudflare 拦截汇总**：
| 程度 | 站点 | 说明 |
|------|------|------|
| ❌ 整站 JS 挑战不可过 | ProgArchives | 靠 RSS 替代 |
| ❌ 详情页 CF 403 | All About Jazz、Resident Advisor | 列表页 metadata 够用 |
| ✅ 原 ASN 黑名单，现可过 | Boomkat | Camoufox fingerprint 绕过，已恢复 |
| ✅ 偶发 paywall/CF，现更稳定 | The Quietus | Camoufox 提升成功率 |

### ⚠️ 新增站点：RSS 必须验证再提交

**不要猜测 RSS 地址**。每次添加新站点时，先用 `curl` + `feedparser` 验证 RSS 是否有效：

```bash
# 测试 RSS
curl -sL --max-time 10 "https://site.com/feed/" | head -5
# 看到 <?xml / <rss / <feed → 有效
# 看到 DOCTYPE / 403 / 404 → 无效
```

如果 RSS 返回 403 或 404，必须改为 `has_rss: false` + `crawl_strategy: playwright_headless`。**宁可用 Camoufox 爬，也不要猜一个错的 RSS 放上去。**

详见 `references/rss-verification.md`。

### ⚠️ Fluid Radio — 静态存档库

Fluid Radio 的 RSS feed 灌入的是 **2013–2022 年全部历史存档**（671 条），站点本身可能已停更，后续爬虫不会抓出新内容。

**处理方式**：sites.json 中 `crawl_strategy: "skip"`。Aggregator **不**从 `fluid_radio_reviews.json` 常规参与评分，而是在推荐生成时额外从该文件**随机抽取 2–3 条**加入推荐池：
- 抽取时优先选 `type: review`、标签匹配实验/声景/环境方向的条目
- 在 markdown 中标注来源为 `[Fluid Radio Archive]`，与当期新内容分开

### ⚠️ The Wire — 特稿/专题格式，非传统乐评

The Wire 有两大板块：

| 板块 | 访问性 | 内容类型 |
|------|--------|---------|
| **In Writing**（`/in-writing/`） | ✅ 完全公开，无需付费 | 特稿、专栏、评论、访谈（如 Bryce Dessner 乐评） |
| **Soundcheck / Magazine** | ❌ 印刷版付费墙后 | 传统专辑乐评，无法爬取 |

我们的 scraper 抓取 **In Writing** 板块的内容，通过 RSS（`https://www.thewire.co.uk/home/rss`）获取。

**RSS 特点**（verified 2026-05-14）：
- RSS feed 有 **91 条** 条目，每条 `<description>` 的 **CDATA** 字段含 5K-20K 字符的完整正文
- feedparser 的 `summary`/`summary_detail.value` 属性返回全文（strip CDATA 标记）
- pubDate 格式标准，可正常解析

**内容不是乐评而是特稿**——Scraper 输出时需处理为 `type: feature` 格式：
- `album` = 文章标题
- `artist` = `"The Wire - {section}"`（section 从 URL 路径推断）
- `score` = null（无评分）
- `excerpt` = strip HTML 后取前 500 字
- `type` = `"feature"`

**节/事判断（从 URL）**：
- `/in-writing/columns/` → Column
- `/in-writing/essays/` → Essay
- `/in-writing/the-portal/` → Portal
- `/in-writing/interviews/` → Interview
- `/in-writing/blog/` → Blog
- `/audio/tracks/` → Audio（Tracks）
- `/audio/on-air/` → Radio
- `/galleries/` → Gallery

**聚合器中展示**：特稿在推荐 markdown 中加 `[FEATURE]` 前缀，与乐评分开展示。

- `references/the-wire-site-config.md` — 2026-05-14 The Wire 重新评估：RSS 91 条含全文，In Writing 板块可访问，非传统乐评，scraper 输出 `type: feature`
- `references/all-about-jazz-site-config.md` — AAJ 列表页可访问但详情页 Cloudflare 保护，entry tag 匹配修复，评分处理
- `references/tracklist-sources.md`

### ⚠️ The Quietus — Camoufox 下更稳定

The Quietus 有 paywall，但 `browser_navigate` 访问 `/columns/quietus-reviews/` 后，cookie 过期前可以抓取部分正文。Camoufox Python 服务器版提供更好的 stealth，此站点抓取成功率有所提升。如果 scraper 任务仍因 CF/paywall 崩溃：先 `kanban unblock` 再 `kanban reclaim`，不要直接归档。

### ⚠️ Musique Machine — 电影/音乐混合，需过滤非音乐条目

**Scraper 行为**：从列表页提取元数据，excerpt 为空字符串。

**评分处理**：SITE_TAGS 基线 2（avant-jazz/world-jazz 匹配），entry 标签 fusion + avant-jazz + world-jazz 各匹配 → entry_match=3，tm=5，cdb=1（jazz + world 双域）。修正后稳定 ★6。

**已知限制**：
- 无 excerpt → CQ=0，上限受站点基线约束
- 条目标签全是站点级 tags，不是条目级
- 用「All About Jazz 推荐（详情页受 Cloudflare 保护，无法提取原文）」替代中文总结

**过滤方法**：scraper body 模板已内置非音乐过滤步骤：提取标题后，如果 `artist` 或 `album` 包含 `(BLU-RAY`、`(UHD`、`(VOD)`、`(DVD` 等关键词，跳过该条目。

**标题格式**（用于区分音乐/电影）：
| 类型 | 标题模式 | 示例 |
|------|---------|------|
| 🎵 音乐 | `ARTIST — ALBUM TITLE` | `ANDREW LILES — NEITHER PRECIOUS NOR NOBLE` |
| 🎬 电影 | `FILM — FILM(BLU-RAY/UHD/VOD/DVD)` | `THE GHOST — THE GHOST(UHD, BLU-RAY, & CD)` |

**配置**：`reviews_url: https://www.musiquemachine.com/reviews/`（不是首页），`crawl_strategy: playwright_headless`，tier: B。

详情见 `references/musique-machine-structure.md`。

### ⚠️ All About Jazz (AAJ) — 详情页 Cloudflare 保护（2026-05-19 重新验证）

AAJ 的 `/reviews` 列表页可正常访问（可提取 album、artist、tags、date），但单个 review 页面 `/review/{slug}` 有强 Cloudflare 保护。**Camoufox Python 服务器版（2026-05-19）重新确认**：仍无法绕过。RSS 全部返回 403。

**Scraper 行为**：从列表页提取元数据，excerpt 为空字符串。

**评分处理**：SITE_TAGS 基线 2（avant-jazz/world-jazz 匹配），entry 标签 fusion + avant-jazz + world-jazz 各匹配 → entry_match=3，tm=5，cdb=1（jazz + world 双域）。修正后稳定 ★6。

**已知限制**：
- 无 excerpt → CQ=0，上限受站点基线约束
- 条目标签全是站点级 tags [\"jazz\", \"fusion\", \"avant-jazz\", \"world-jazz\"]，不是条目级
- 用「All About Jazz 推荐（详情页受 Cloudflare 保护，无法提取原文）」替代中文总结
- 详情见 `references/all-about-jazz-site-config.md`

### ⚠️ Resident Advisor (ra.co) — 电子/舞曲核心站，详情页 Cloudflare 保护

RA 的 `/reviews` 列表页可正常访问（含内联简短 excerpt），但单个 review 详情页有 Cloudflare 403 保护。Camoufox Python 服务器版（2026-05-19 重新验证）：**详情页仍不可达**。

**Scraper 行为**：从列表页提取 metadata + 内联 excerpt（约 20-50 字短语，如 "Ice-cold 808s from electro's new prince"）。不需要点进详情页。

**评分处理**：
- 标签 `electronic/club/experimental` → site_base=1
- excerpt 短（<150 字）→ CQ=1，penalty +1
- 稳定 ★4-5

**注意事项**：
- RA 列表页需要处理 cookie consent banner（有 cookie 弹窗）
- 只提取 3 天内条目

### ⚠️ ProgArchives — Cloudflare JS 挑战（无解，走 RSS）

ProgArchives 整个站点触发 Cloudflare JS 挑战（`Just a moment...` 验证页），Camoufox 也无法绕过（2026-05-19 验证）。但 RSS 通过 Feedburner 正常可用。

**Scraper 策略**：走 RSS（`feeds.feedburner.com/Progarchives/newreleases`），已验证 24 条可手动拉取。`crawl_strategy: http_get`（实际走 RSS 解析），不做 Playwright 尝试。

## 非音乐内容过滤（通用规则）

所有 scraper 任务必须遵循以下过滤规则，排除非音乐内容：

```
如果条目标题/artist/album 匹配以下模式之一，说明这是电影/碟片评测，不是音乐，跳过：
  - (BLU-RAY、 (BLU RAY、 (UHD、 (VOD)、 (DVD、 BLURAY (大小写不敏感)
  - 标题后缀 = "(Blu-ray)", "(Blu ray)", "(UHD)", "(VOD)", "(DVD)"
```

这条规则已内置于 `kanban-batch-scrape.py` 的 scraper body 模板中（步骤 8），对所有站点生效。添加新站点时，如果该站同时有电影和音乐内容，需要确保这条规则能覆盖。

## Scraper 模板指令改进（2026-05-14）

今天系统性检查了 42 个活跃站点后，在 scraper body 模板中增加了以下改进：

### Cookie 墙处理（所有站点）
```markdown
browser_navigate 之后，检查页面是否有 cookie consent banner
查找方式：找包含 "cookie" 的文本 + "agree" / "accept" / "I agree" 的按钮或链接
如果找到任意 "Agree" / "Accept" / "I agree" 按钮，立即点击，等 1 秒让 banner 消失
然后再继续提取内容
```
很多 DJ/音乐站（Resident Advisor、Bandcamp Daily）有 Cookie 弹窗，之前 scraper 可能因弹窗挡在内容前而返回空。

### RSS 全文提取（The Wire 模式）
```markdown
许多站的 RSS 在 <description> CDATA 字段有完整正文（如 The Wire 5K-20K 字符）。
用 feedparser 的 summary 字段获取全文，strip HTML 后取前 500 字填入 excerpt。
如果没有正文仅摘要则用摘要。
```
The Wire 的 RSS CDATA 中含有数千字的全文，但 feedparser 默认 description 字段可能为 None。实测可用 `summary` 或 `summary_detail.value` 直接取到解 CDATA 后的 HTML 正文。

### 特稿/专题格式处理
```markdown
如果文章不是传统乐评格式（特稿/专题/访谈/音频节目）：
  将文章标题填入 album，栏目名或分类填入 artist
  type 设为 "feature"，score 设为 null
```
The Wire 的 In Writing 板块、The Quietus 的专栏/访谈等都不是 album+artist 的传统格式。Agent 需要判断格式差异并输出 type="feature"。

### Camoufox 列表页只爬不点
今日发现多个站点（All About Jazz）详情页被 Cloudflare 保护，列表页可访问且有条目数据。Scraper 指令已明确：
- 只浏览列表页前 2 页
- 不需要点进详情页抓全文
- 从列表页提取 album/artist/date/tags 即可
- excerpt 可为空

### Songlines / DownBeat URL 修复
- **Songlines**：`/category/reviews` → `/reviews-hub`（旧 URL 返回 500 错误，已修复）\n- **DownBeat**：首页 `/` → `/reviews`（旧 URL 从首页无法找到 review 列表，已修复）\n- 两个 URL 已在 sites.json 中修复并生效（2026-05-14），多次 cron 验证稳定

## 类型分类规则（`type` 字段）

scraper 输出 JSON 后，aggregator 需要自动推断 `type` 字段：

| type | 判断条件 | 是否参与推荐 |
|------|----------|-------------|
| `review` | `artist` 和 `album` 字段都有内容 | ✅ 参与评分 |
| `feature` | `album` 字段为空或为特辑标题（如 `"Spool's Out: ..."`、`"Reissue of the Week: ..."`），但 `artist` 有内容 | ✅ 参与评分（特辑常提及具体专辑），Markdown 输出时加 `▸ [FEATURE]` 前缀 |
| `tracklist` | 来源是 The Wire 的 tracklist 格式 | ✅ 参与评分，Markdown 输出时加 `▸ [TRACKLIST]` 前缀 |

**判断优先级**：先判断 tracklist（来源字段），再判断 review vs feature（album 字段是否为空/特辑格式）。

## 评分公式 v2（2026-05-14 重写）

### 背景：为什么重写

旧公式定义了 7 个评分维度，但在实际数据中只有 **2 维在工作**：

| 维度 | 理论上 | 实际上 | 原因 |
|------|--------|--------|------|
| CQ (critic_quality) | 0-5 | 90% 有值 | ✅ excerpt 长度总是有的 |
| **TM (taste_match)** | **0-5** | **仅 23%** | ❌ 78% 的条目 scraper 没提取到结构化标签 |
| NOV (novelty) | 0-3 | 仅 12% | ❌ 关键词列表太窄（只有 8 个） |
| CDB (cross_domain) | 0-3 | 仅 13% | ❌ 只查标签不查正文 |
| REG (regional) | 0-2 | ~0% | ❌ 只查标签不查正文国家/地名 |
| MP (mainstream_penalty) | 0-3 | ~0% | ❌ 这些站本来就不存在主流内容 |
| DR (synth_dungeon_downgrade) | 0-2 | ~0% | ❌ 同上 |

**最大问题**：TM=0 不代表"不匹配口味"。很多重要站点（world_music_central、roots_world、a_closer_listen）在 sites.json 中标注了 experimental/avant-garde 标签，但 scraper 提取的 entry-level tags 不包含这些关键词。例如 **Jonny Greenwood（Radiohead）的 qawwali fusion 作品 TM=0**，Omar Sosa TM=0，Julius Eastman TM=2（仅因 avant_music_news 的 entry tags 恰好匹配）。

旧公式的有效公式实际上退化成了：
```
total ≈ CQ(0-5) + TM(0-5 但只有 23% 有值) - 1(if excerpt < 100字)
```

### 新公式（v2）

```
total_score = critic_quality(0-3) + taste_match(0-5) + novelty(0-3)
             + cross_domain_bonus(0-3) + regional_bonus(0-2) 
             - mainstream_penalty(0-3) - synth_dungeon_downgrade(0-2)
```

### critic_quality (0-3，上限从 5 降低)

旧公式 CQ=5 只需 excerpt 500 字，导致 excerpt 长度垄断评分。新公式使用对数缩放：

- 150 字 = 1，300 字 = 2，450+ 字 = 3
- 上限从 5 降到 **3**，减少长度影响

### taste_match (0-5，三层叠加)

旧公式只查 entry 标签（78% 条目 TM=0）。新公式使用三层评分：

**第 1 层：站点基线**（0-2，从 sites.json 标签推断）

| 站点标签特征 | 基线 | 示例站点 |
|-------------|------|---------|
| 含 experimental/avant-garde/free jazz/ambient/drone/industrial/noise/improvisation/sound art/field recording | +2 | musique_machine, squids_ear, igloo_magazine, free_jazz_blog, avant_music_news, the_quietus |
| 含 world/folk/electronic/minimalist/ritual/weird | +1 | hhv_mag, world_music_central, roots_world, a_closer_listen |
| 不含上述（古典/主流爵士） | 0 | the_classic_review, jazz_journal, downbeat |

**第 2 层：entry 标签匹配**（0-3，与旧公式相同）
扫描 entry 的 `tags`/`genre` 字段，匹配 avant_kw 列表。

**第 3 层：正文扫描**（0-1）
如果第 2 层得分 < 2，扫描 excerpt 正文中 avant-garde 关键词。正文中有 >=2 个匹配 → +1。

最终 tm = min(5, site_base + entry_tag_match + excerpt_match)

### novelty (0-3，关键词扩充)

旧公式（8 个）：unique, rare, first, unusual, innovative, cross-cultural, world, ritual
新公式（17 个）：

```
unique, rare, first, unusual, innovative, cross-cultural, world, ritual,
exploration, boundary, genre-defying, groundbreaking, fusion, breakthrough,
singular, unconventional, pushing
```

### cross_domain_bonus (0-3，同时扫描正文)

旧公式只查 entry 标签。新公式同时扫描 excerpt 正文：

```
domain_map = {
  "jazz": [jazz, improvisation],
  "electronic": [electronic, idm, glitch, ambient, drone, synth],
  "world": [world, african, asian, latin, folk, india, oriental],
  "classical": [classical, chamber, minimalist, orchestral, solo, piano]
}
```

如果 entry 标签不足以判断跨域（`len(domains) < 2`），从正文补充证据。

### regional_bonus (0-2，扫描文本非标签)

旧公式只查 tag 中标准区域关键词。新公式扫描三个文本来源（entry tags + excerpt + artist 字段）：

- **高价值**（region 级）：southeast asia, south america, middle east, central asia → +2
- **低价值**（country 级）：argentina, brazil, india, palestine, turkey, japan, korea, thailand, mexico, cuba, morocco, egypt, china, chile, colombia, indonesia → +1

### mainstream_penalty (0-3) — 不变

- 3：纯流行、无实验性的 mainstream indie
- 2：有实验标签但内容空洞
- 1：偏主流但有可取之处
- 0：不属于 mainstream penalty 范围

### Synthwave / Dungeon Synth 降权（synth_dungeon_downgrade, 0-2）— 不变

- Synthwave / Retrowave：只有 80s nostalgia aesthetic，没有明显声音创新 → -1；评论只是 "fun", "nostalgic", "retro vibes" → -1
- Dungeon Synth / Dark Ambient：只是低保真循环 pad 堆叠，没有明显叙事感/音色设计/世界构建 → -1

### ⚠️ 实现验证

2026-05-14 实测（113 条音乐条目）：

| 条目 | 旧分 | 新分 | 简评 |
|------|------|------|------|
| Andrew Liles — 20 种金属声源 | ★9 | ★10 | ✅ 合理提升 |
| Oud for Palestine — Saied Silbak | ★5 | ★9 | ✅ 世界音乐+地缘政治受认可 |
| Walkman — Speedy J | ★5 | ★8 | ✅ IDM 传奇 |
| Omar Sosa — 古巴钢琴即兴 | ★4 | ★8 | ✅ 知名艺术家 |
| Ranjha — Jonny Greenwood | ★5 | ★7 | ✅ Radiohead 成员 qawwali 融合 |
| Julius Eastman Vol.5 | ★5 | ★6 | ✅ 前卫传奇 |
| Ava Mendoza — 前卫吉他 | ★4 | ★6 | ✅ |
| Alexander Hawkins | ★3 | ★7 | ✅ 前卫爵士钢琴 |
| Laurie Anderson | ★3 | ★5 | 仍偏低（excerpt 仅 139 字）|
| Anthony Braxton | ★3 | ★5 | 仍偏低（excerpt 仅 226 字）|

覆盖率：**24 条 >=6** vs 旧公式 9 条，翻倍多。

评分公式实现在 `kanban-batch-scrape.py` 的 aggregator 模板内，函数名 `score_review(r, site_id)`。

## LLM 中文总结（聚合器核心）

aggregator 模板内嵌的 `summarize_cn` 函数使用 **MiniMax M2.7** 为每条通过评分≥6 的推荐生成 1-2 句中文总结。

**⚠️ 不要用关键词拼接做总结** — `gen_cn_fallback_v1` 是兜底函数，输出的是"低频嗡鸣与氛围纹理；噪音/工业粗粝质感"这种无关痛痒的模板化文本，用户明确拒绝。**正常路径必须走 LLM API。**

### API 配置（已验证）

```python
MINIMAX_CN_API_KEY = os.environ.get("MINIMAX_CN_API_KEY", "")
# 兜底：从 .env 文件读取
if not MINIMAX_CN_API_KEY:
    with open("/home/liyifan/.hermes/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "MINIMAX_CN_API_KEY" in line:
                MINIMAX_CN_API_KEY = line.split("=", 1)[1].strip().strip("'\"").strip()

LLM_API_URL = "https://api.minimaxi.com/v1/chat/completions"
LLM_MODEL = "MiniMax-M2.7"
```

### 常犯错误（三连坑）

| 配置 | 错误写法 | 正确写法 |
|------|---------|---------|
| 环境变量名 | `MINIMAX_API_KEY` ❌ | `MINIMAX_CN_API_KEY` ✅ |
| API URL | `api.minimax.chat/...` ❌ | `api.minimaxi.com/v1/chat/completions` ✅ |
| 模型名 | `MiniMax-M2-7B` ❌ | `MiniMax-M2.7` ✅ |

**可用性验证**（2026-05-14 已修复）：至少 3 周没人发现这三项全错——因为 API 调用静默失败后降级到关键词兜底，不报错。症状是中文总结全是模板化废话，没有实质内容。修复后正常工作。

### System Prompt（已验证）

```
你是一位专业华语乐评人。用1-2句简洁的中文总结这张专辑的核心特点：
艺人是谁、什么声音风格、最亮眼之处。不要空话套话。
```

### 注意事项

- 每条总结约需 **5-10 秒** API 延迟。13 条通过 ≈ 2 分钟
- 如果 excerpt > 1000 字符会被截断
- MiniMax M2.7 有时会在输出前加 ` thinking... response` 思考前缀，需要 strip 掉
- **⚠️ 更严重的 thinking 泄露问题**：MiniMax M2.7 有时会输出**完整的多段内部独白**（包含 "We need to produce a 1-2 sentence Chinese summary..."、逐条分析要点、中英文交替的自我论证），而非仅返回最终总结。代码中只 strip ` thinking... response` 前缀不够，需要额外过滤。
  ```python
  # 过滤 MiniMax thinking 泄露的修复
  def clean_summary(text):
      if not text:
          return ""
      # Strip thinking prefix
      if " response" in text:
          text = text.split(" response", 1)[-1].strip()
      # Strip full internal monologue (model reasoning about what to write)
      monologue_markers = ["We need to", "我们应该", "Thus:", "1-2 sentence",
                           "First sentence", "Second sentence", "we can give",
                           "we should mention", "maybe:"]
      has_monologue = any(m in text for m in monologue_markers)
      if has_monologue:
          # Try to extract only the actual summary sentences (those ending with 。)
          import re
          sentences = re.findall(r'[^。]+。', text)
          # Filter out sentences that look like instructions
          actual = [s.strip() for s in sentences
                    if not any(m in s for m in ["We need", "我们应该", "Thus:",
                                                  "First sentence", "Second sentence",
                                                  "we can give", "we should mention"])]
          if actual:
              return "；".join(actual[:2])
          return ""
      return text
  ```
- LLM 可以自主区分电影和音乐 — 对 `(BLU-RAY` 等电影条目，它会输出"这是电影而非音乐专辑"

详情见 `references/minimax-summarization-api.md` 和 `references/minimax-thinking-leakage.md`。

## 推荐原因写法规范

✅ 把自由爵士管乐、粗粝电子纹理和近乎仪式性的打击循环缝在一起，张力非常足。
✅ 在南岛/东南亚打击乐语感上叠加氛围电子与现场采样，既有地景感也有现代制作感。
✅ 用 darksynth / horror-synth 的重型音色和明确的专辑结构把复古合成器语言推向更强的戏剧张力。
✅ 不是单纯的 lo-fi fantasy 氛围堆叠，而是有明确场景感、叙事感和声音层次的 dark ambient / dungeon synth 作品。
❌ 很好听。很值得一听。很前卫。口碑不错。

## 输出结构（唯一输出）

**aggregator 直接写 recommend/{DATE}.md 作为唯一 markdown 输出**，不在日期子目录下重复写一份。

| 文件 | 路径 | 说明 |
|------|------|------|
| recommend markdown | `recommend/{YYYY-MM-DD}.md` | 唯一 markdown 输出，含 ★10/8/6 分级 |
| aggregator JSON | `2026/{MM}/{YYYY-MM-DD}/aggregated.json` | 全量去重评论 |
| filtered JSON | `2026/{MM}/{YYYY-MM-DD}/filtered.json` | >=6 分评论 |
| scraper JSON | `2026/{MM}/{YYYY-MM-DD}/{site_id}_reviews.json` | 各站原始输出 |

**Telegram 推送**：`recommend/{DATE}.md` 内容作为消息体发送。

## 站点诊断（爬虫空结果排查）

当一个站点返回空爬取结果时，不要只查一两个站就下结论。系统性地检查所有异常站：

1. 检查 JSON 文件是 `[]` 还是 `{"excerpt": ""}`
2. 测试 RSS 是否有效 + 最近内容日期
3. 测试 `reviews_url` 的 HTTP 状态码
4. 用 browser_navigate 浏览确认网站结构
5. 分类定论：URL 错了？RSS 坏了？Cloudflare？低频更新？Agent bug？

**详见** `references/site-investigation-methodology.md` 和 `references/scraper-diagnostics-2026-05-14.md`（含 42 站全量 audit 结果）。

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

### Step 1 — 同步配置 + skill + 脚本

**每次 cron 触发必须首先从 music-record 拉取最新版本**，skill 和 py 跟着每日结果一起版本控制：

```bash
# 拉取 music-record 完整更新（sites.json + skill + 脚本）
cd /home/liyifan/music-record && git pull origin main

# 同步 skill 到本地 hermes skills 目录
mkdir -p ~/.hermes/skills/music/music-daily-recs
cp /home/liyifan/music-record/skills/music/music-daily-recs/SKILL.md \
   ~/.hermes/skills/music/music-daily-recs/

# 同步脚本到本地 bin 目录
cp /home/liyifan/music-record/bin/kanban-batch-scrape.py \
   ~/.local/bin/kanban-batch-scrape.py

# 同步 sites.json（如有更新）
mkdir -p ~/.minimax/music-sites
cp /home/liyifan/music-record/sites.json ~/.minimax/music-sites/ 2>/dev/null || true
```

> **为什么要一起拉？** skill 和 py 在 music-record 仓库里版本控制，每次 bug 修复或 workflow 改进都 commit 在同一个 repo。cron 触发时必须拉到最新版本再执行，否则脚本和 skill 脱节。

sites.json 路径：`/home/liyifan/.minimax/music-sites/sites.json`
skill 路径：`~/.hermes/skills/music/music-daily-recs/SKILL.md`
脚本路径：`~/.local/bin/kanban-batch-scrape.py`
Output 路径：
- `~/music-record/2026/{MM}/{YYYY-MM-DD}/` — 当天 scraper JSON + aggregated.json + filtered.json（不含 markdown，markdown 仅在 recommend/）
- `~/music-record/recommend/{YYYY-MM-DD}.md` — 唯一 markdown 输出（直接推送 Telegram）

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

**💡 SQLite 直接轮询（推荐，比 hermes kanban list 快 10x）**：
```bash
# 快速计数 scraper 状态
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
status = conn.execute(\"SELECT status, COUNT(*) FROM tasks WHERE title LIKE 'scrape:%' GROUP BY status\").fetchall()
conn.close()
print(status)
# 输出类似: [('done', 42), ('running', 0), ('todo', 0)]
" 2>/dev/null

# 检查 aggregator 状态
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
rows = conn.execute(\"SELECT title, status, id FROM tasks WHERE title LIKE 'aggreg%'\").fetchall()
conn.close()
for r in rows:
    print(f'{r[1]:<10} {r[0]} ({r[2][:12]}...)')
" 2>/dev/null

# 循环轮询（每 30s，直到全部 done）
python3 -c "
import sqlite3, time
target = 42
while True:
    conn = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
    d = conn.execute(\"SELECT status, COUNT(*) FROM tasks WHERE title LIKE 'scrape:%' GROUP BY status\").fetchall()
    conn.close()
    if any(s[0]=='todo' or s[0]=='running' for s in d):
        print(f'[{\"A\" if int(time.time())%2 else \"B\"}] {d}')
        time.sleep(30)
    else:
        print(f'ALL DONE: {d}')
        break
" 2>/dev/null
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
> ⚠️ 需要使用 LLM-based 中文总结（旧版关键词拼接已被用户拒绝）。见 `references/minimax-summarization-api.md` 获取完整配置。

**推荐 LLM-based 完整 fallback（优先）**：
将 `gen_summaries.py` 写入临时文件并执行，生成真正的 MiniMax M2.7 中文总结，再构建 markdown。参见 2026-05-19 session 的实际做法：

```bash
# 关键步骤序列（替换 YYYY-MM-DD 为实际日期）：
TODAY="YYYY-MM-DD"  # 改为实际日期
DATE_DIR="/home/liyifan/music-record/2026/${TODAY:5:2}/${TODAY}"

# 1. 聚合（读取所有 scraper JSON → dedup → 评分 → filtered.json）
cd /home/liyifan/music-record && python3 -c "
import json, os, glob
# ...（同下方简化版中的聚合逻辑）
" 

# 2. 生成中文总结（写临时脚本 → 执行）
cat > /tmp/gen_summaries_${TODAY}.py << 'PYEOF'
import json, os, requests, re, sys

# MiniMax API 配置（从 auth.json 读取）
with open(os.path.expanduser('~/.hermes/profiles/scraper/auth.json')) as f:
    auth = json.load(f)
key = auth.get('credential_pool', {}).get('minimax-cn', {})
MINIMAX_CN_API_KEY = key.get('api_key', '')

LLM_API_URL = 'https://api.minimaxi.com/v1/chat/completions'
LLM_MODEL = 'MiniMax-M2.7'

def call_llm(prompt):
    resp = requests.post(LLM_API_URL, headers={
        'Authorization': f'Bearer {MINIMAX_CN_API_KEY}',
        'Content-Type': 'application/json'
    }, json={
        'model': LLM_MODEL,
        'messages': [
            {'role': 'system', 'content': '你是一位专业华语乐评人。用1-2句简洁的中文总结这张专辑的核心特点：艺人是谁、什么声音风格、最亮眼之处。不要空话套话。'},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 300,
        'temperature': 0.1
    }, timeout=30)
    return resp.json()['choices'][0]['message']['content']

def clean_summary(text):
    # 过滤 MiniMax thinking 泄露
    if not text: return ''
    if ' response' in text:
        text = text.split(' response', 1)[-1].strip()
    monologue = ['We need to', '我们应该', 'Thus:', '1-2 sentence',
                 'First sentence', 'Second sentence', 'we can give',
                 'we should mention', 'maybe:']
    if any(m in text for m in monologue):
        sentences = re.findall(r'[^。]+。', text)
        actual = [s.strip() for s in sentences
                  if not any(m in s for m in monologue)]
        return '；'.join(actual[:2]) if actual else ''
    return text

# ... 读取 filtered.json，逐个调用 LLM，保存 summaries.json
PYEOF
python3 /tmp/gen_summaries_${TODAY}.py

# 3. 构建 markdown（读取 summaries.json 插入中文总结）
python3 -c "
import json
with open('/tmp/summaries_${TODAY}.json') as f:
    summaries = json.load(f)
# ... 构建 recommend/${TODAY}.md
"
```

⚠️ 每条 LLM 调用约 5-10 秒。写独立脚本而不是内联 heredoc，避免 shell 转义问题。
⚠️ 注意处理 `clean_summary` — MiniMax 的 thinking 泄露可能包含完整的多段内部独白。
⚠️ 在 cron job 中使用 `background` + `notify_on_complete` 运行 LLM 生成，设置 timeout=600。

**简化版 fallback（不含 LLM 总结的轻量版，仅供快速验证数据量）**：

```bash
cd ~/music-record && python3 - << 'PYEOF'
import json, os, glob
from datetime import date, datetime

today = "2026-05-11"  # 替换为实际日期！！
date_dir = f"2026/{today[5:7]}/{today}"
files = sorted(glob.glob(f"{date_dir}/*_reviews.json"))

entries = []
for f in files:
    site = os.path.basename(f).replace("_reviews.json", "")
    try:
        with open(f) as fh:
            data = json.load(fh)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict): item["_site"] = site; entries.append(item)
        elif isinstance(data, dict):
            for key in ["reviews", "articles"]:
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        if isinstance(item, dict): item["_site"] = site; entries.append(item)
    except: pass

seen = {}
for e in entries:
    key = ((e.get("album") or "").strip().lower(), (e.get("artist") or "").strip().lower())
    if not key[0] and not key[1]: continue
    if key not in seen or (e.get("score",0) > seen[key].get("score",0)):
        seen[key] = e
deduped = list(seen.values())

# ── 评分函数（与主模板一致）──
def score_review(r):
    excerpt = r.get("excerpt","") or ""
    tags_raw = r.get("tags","") or ""
    tags = [t.lower().strip() for t in tags_raw.split(",")] if isinstance(tags_raw,str) else tags_raw
    tags_str = tags_raw.lower() if isinstance(tags_raw,str) else " ".join(t.lower() for t in tags_raw).lower()
    elen = len(excerpt)
    cq = min(5, elen // 100) if elen > 0 else 0
    avant_kw = ["experimental","avant-garde","free jazz","electroacoustic","drone","ambient","idm","glitch","industrial","sound art","modern composition","field recording","improvisation","noise","ritual","dark ambient","dungeon synth","darksynth","synthwave"]
    tm = min(5, sum(1 for t in tags for k in avant_kw if k in t))
    novelty_kw = ["unique","rare","first","unusual","innovative","cross-cultural","world","ritual"]
    nov = min(3, sum(1 for kw in novelty_kw if kw.lower() in excerpt.lower()))
    domains = set()
    for t in tags:
        if any(k in t for k in ["jazz","improvisation"]): domains.add("jazz")
        if any(k in t for k in ["electronic","idm","glitch","ambient","drone"]): domains.add("electronic")
        if any(k in t for k in ["world","african","asian","latin","folk"]): domains.add("world")
        if any(k in t for k in ["classical","chamber","minimalist"]): domains.add("classical")
    cdb = max(0, len(domains) - 1) if len(domains) > 1 else 0
    reg_kw = ["southeast asia","south america","africa","middle east","central asia","southeast asian"]
    reg = 2 if any(kw in " ".join(tags) for kw in reg_kw) else (1 if any(kw in excerpt.lower() for kw in ["asia","africa","latin"]) else 0)
    mp = 0
    el_lower = excerpt.lower()
    if all(k in el_lower for k in ["pop","mainstream"]): mp = 3
    elif "pop" in el_lower and "experimental" not in el_lower and "avant" not in el_lower: mp = 2
    elif "mainstream" in el_lower and "experimental" not in el_lower: mp = 2 if "indie" in el_lower else 1
    dr = 0
    if "synthwave" in tags_str or "retrowave" in tags_str:
        if not any(k in el_lower for k in ["innovative","modern","experimental","composition","texture","design"]):
            if all(k in el_lower for k in ["retro","nostalgic"]): dr += 1
            if "vibes" in el_lower and "sound" not in el_lower and "textur" not in el_lower: dr += 1
    if "dungeon synth" in tags_str or "dark ambient" in tags_str:
        if not any(k in el_lower for k in ["texture","layer","narrative","worldbuilding","composition","ritual"]) and ("lo-fi" in el_lower or "noise" in el_lower): dr += 1
    pen = 1 if cq <= 1 else 0
    return max(0, cq + tm + nov + cdb + reg - mp - dr - pen)

for r in deduped:
    r["total_score"] = score_review(r)

scored = sorted(deduped, key=lambda x: x["total_score"], reverse=True)
passed = [r for r in scored if r["total_score"] >= 6]
print(f"Total: {len(entries)}, Unique: {len(deduped)}, Passed >=6: {len(passed)}")

os.makedirs(date_dir, exist_ok=True)
with open(f"{date_dir}/aggregated.json", "w") as f:
    json.dump(deduped, f, ensure_ascii=False, indent=2)

# 写 markdown（用 LLM API 生成真正的中文总结，见 references/minimax-summarization-api.md）
lines = [f"# Daily Music Recommendations -- {today}\\n"]
top = [r for r in passed if r["total_score"] >= 11]
mid = [r for r in passed if 8 <= r["total_score"] <= 10]
low = [r for r in passed if 6 <= r["total_score"] < 8]
for group_title, group in [("## Top Picks\\n", top), ("## Notable\\n", mid), ("## Also\\n", low)]:
    if not group: continue
    lines.append(group_title)
    for r in group:
        album = r.get("album","") or "(unknown)"
        artist = r.get("artist","") or "(unknown)"
        source = r.get("source","") or r.get("_site","") or r.get("site_id","") or "unknown"
        url = r.get("url","") or "#"
        excerpt = r.get("excerpt","") or ""
        artist_album = f"{album} -- {artist}"
        # 用 LLM 生成总结（见 references/minimax-summarization-api.md）
        lines.append(f"**{album} -- {artist}** [★{r['total_score']}], {source}")
        lines.append(f"[阅读原文]({url})")
        lines.append(f"> {excerpt}" if excerpt else "")
        lines.append("")

md_path = f"/home/liyifan/music-record/recommend/{today}.md"
with open(md_path, "w") as f:
    f.write("\\n".join(lines))
print(f"Done: {md_path}")
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
4. 40 个 scraper 落入 `◻ todo`（因 dispatcher 已满载，new task 等待），剩余 2 个继续运行
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
3. 输出到 {date_dir}/aggregated.json、{date_dir}/filtered.json
4. recommend 文件写入绝对路径：/home/liyifan/music-record/recommend/{DATE}.md（唯一 markdown 输出）
```

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

### ⚠️ `agg_body` 模板格式化陷阱（`%` 与 f-string）

`agg_body` 是 `kanban-batch-scrape.py` 最脆弱的代码段 — 它是一个大型 Python 多行字符串（~250 行），同时包含：
- **外层文本**：markdown 说明 + bash/git 命令（用 `%s`/`%d` 占位符）
- **内嵌 Python 代码**（在 ` ```python ` 代码围栏内）：聚合器 agent 执行的实际逻辑

这两层有不同的变量替换需求，是 bug 高发区。

#### 场景回顾：从 f-string 到 `%` 格式化的迁移

最初 `agg_body` 用 f-string 拼接，但花括号嵌套（外层 `{var}` + 内层留给下一级模板的 `{N}`）导致 `f-string: empty expression not allowed` 错误。改用 `%` 格式化后，f-string 的花括号问题解决了，但引入了新的陷阱。

**旧问题（f-string 模式）**：
- 直接写 `metadata={"total": {N}}` → Python 把 `{N}` 当成插值表达式，语法错误
- `{` 后面必须跟空格，或用 `{{` 转义，但 `{{"total"` 还是会解析错
- 花括号嵌套的解析规则非常脆弱

**新问题（`%` 格式化模式）**：

#### 错误 1：`%s`/`%d` 计数不匹配

**场景**：模板有 N 个 `%s`/`%d` 占位符，但 `agg_body % (...)` 的元组提供了 M != N 个值。

**现象**：`TypeError: not enough arguments for format string`（值太少）或 `TypeError: not all arguments converted during string formatting`（值太多）。

**2026-05-14 实测**：模板有 20 个占位符（13 `%s` + 7 `%d`），格式元组只传了 18 个值。少传的是 `kanban_complete` 行的最后 2 个 `%d`。

**诊断**：
```python
# 用 Python 统计 agg_body 中的 %s/%d 数量
import re
s_count = len(re.findall(r'(?<!%)%s', agg_body))
d_count = len(re.findall(r'(?<!%)%d', agg_body))
print(f"需要 %s={s_count} + %d={d_count} = {s_count+d_count} 个值")
```

**预防**：每次在 `agg_body` 中添加或删除 `%s`/`%d`，必须同步更新 `agg_body % (...)` 元组。没有自动检查，必须手动用 `re.findall` 验证。

#### 错误 2：内嵌 Python 代码中的 `{DATE}`/`{date_dir}` 不是 `%` 占位符

**场景**：`agg_body` 的内嵌 Python 代码块中有：
```python
DATE = "{DATE}"       # 字面量字符串 "{DATE}" ❌
date_dir = "{date_dir}"  # 字面量字符串 "{date_dir}" ❌
```
`%` 格式化只替换 `%s`/`%d`，不替换 `{DATE}`/`{date_dir}`。所以聚合器 agent 执行时，`DATE` 的值是字面字符串 `"{DATE}"`，不是实际日期。

**2026-05-14 实测后果**：`date_dir` 被设为字面字符串 `"{date_dir}"` → `os.listdir("{date_dir}")` → `FileNotFoundError`。`md_path = f".../recommend/{{DATE}}.md"` 输出到 `recommend/{DATE}.md`（字面文件名）。

**修复**：必须改为 `%s` 占位符，并在 `%` 元组中提供对应值：
```python
DATE = "%s"           # 会被替换为 "2026-05-14"
date_dir = "%s"       # 会被替换为 "/home/liyifan/music-record/2026/05/2026-05-14"
```

**规则**：`agg_body` 内的**所有占位符**必须使用 `%s`/`%d` 语法。`%` 格式化的唯一替换语法就是 `%s`/`%d`/`%r`，不能靠 `{var}` 隐式替换。

#### 错误 3：变量遮蔽（`MONTH` 全局 vs 局部）

**场景**：脚本顶部定义了全局 `MONTH = TODAY.strftime("%m")`（值为 `"05"`）。`main()` 函数尾部又有 `MONTH = date_obj.strftime("%Y-%m")`（值为 `"2026-05"`，用于 git 路径）。

**现象**：`UnboundLocalError: cannot access local variable 'MONTH' where it is not associated with a value` — Python 看到 `main()` 内有 `MONTH = ...` 赋值语句，就把 `MONTH` 视为整个函数的局部变量。但 `L84` 的 `date_dir = f".../{MONTH}/..."` 在赋值之前执行，所以报错。

**2026-05-14 实测**：`--confirm` 时脚本崩溃，所有 scraper 任务创建了一半就中止，留下孤立任务。

**规则**：不要在 `main()` 中重新赋值已在模块级定义的变量。改名（如 `git_month`）或声明 `global MONTH`。

#### 错误 4：`passed` 变量作用域泄露

**场景**：`len(passed)` 出现在 `agg_body % (...)` 元组中。但 `passed` 只存在于 `agg_body` 字符串内部（聚合器 agent 的变量），在 `main()` 作用域中不存在。

**现象**：`NameError: name 'passed' is not defined`。

**2026-05-14 实测**：由于错误 3 先触发了 `UnboundLocalError`，这个错误尚未暴露。但它是下一个会触发的错误。

**规则**：`agg_body` 模板中的变量是分开的命名空间。`%` 格式化时使用的值必须在 `main()` 作用域中真实存在，不能用模板内代码定义的变量。

#### 错误 5：函数签名与调用不匹配

**场景**：`gen_cn_fallback(r)` 定义为接受 1 个 dict 参数（通过 `r.get("tags")` 取标签），调用时写成 `gen_cn_fallback(excerpt, artist_album)`（2 个字符串参数）。

**现象**：`TypeError: gen_cn_fallback() takes 1 positional argument but 2 were given`。同时导致 `tags_raw` 永远为 `""`，关键词匹配全部失效。

**修复**：改为 `gen_cn_fallback_v1(excerpt_text, artist_album_str, tags_raw_str="")`，接收 3 个字符串参数，`tags_raw` 作为参数传入而非从 dict 提取。

**规则**：内嵌 Python 代码中的函数签名变化后，必须同步更新所有调用点。如果参数类型变化（dict → strings），依赖 `.get()` 提取的数据需要用参数传递。

#### 综合验证流程

每次修改 `agg_body` 模板后必须完整执行：

```bash
# 1. 语法检查（捕获 f-string、括号、引号问题）
python3 -m py_compile /path/to/kanban-batch-scrape.py

# 2. 模拟 % 格式化（捕获计数不匹配、变量不存在问题）
python3 -c "
import re
with open('/path/to/kanban-batch-scrape.py') as f:
    text = f.read()
lines = text.split('\n')
agg_body = '\n'.join(lines[145:412])  # 行号区间取决于脚本结构
s_count = len(re.findall(r'(?<!%)%s', agg_body))
d_count = len(re.findall(r'(?<!%)%d', agg_body))
print(f'Template has {s_count} %s + {d_count} %d = {s_count+d_count} placeholders')
"

# 3. Dry run（确认输出正常）
python3 /path/to/kanban-batch-scrape.py

# 4. 如果改动了 skill，也同步到 GitHub
cd ~/music-record && \
cp ~/.local/bin/kanban-batch-scrape.py bin/ && \
git add bin/kanban-batch-scrape.py && \
git commit -m "Fix: ..." && \
git push
```

**教训**：dry run 只通过语法的静态检查，不会暴露运行时错误（`%` 格式化时崩溃、`UnboundLocalError`、`NameError`）。这些必须在 `--confirm` 的代码路径中才能发现。每次更改 `agg_body` 必须用**上述完整流程**验证。

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

**五个组成部分**（每次 Pipeline 必须同步更新）：

| 目录 | 内容 | 说明 |
|------|------|------|
| `bin/kanban-batch-scrape.py` | batch 脚本最新版本 | 跟着每日结果一起 commit，cron 触发时拉到本地执行 |
| `skills/music/music-daily-recs/SKILL.md` | skill 最新副本 | 同上 |
| `data/sites.json` | 站点配置 | 从 music-record 同步到 ~/.minimax/music-sites/ |
| `2026/{MM}/{YYYY-MM-DD}/` | 当天乐评原始数据 | scraper JSON + aggregated + filtered + markdown |
| `recommend/YYYY-MM-DD.md` | 每日推荐总结 | **完整全量推荐**，放在仓库根目录 `recommend/` 下 |

> ⚠️ **五部分必须一起 push**：`bin/`、`skills/`、`data/`、`2026/`、`recommend/` 五个目录/文件每次必须同时 commit。

**⚠️ 目录结构规范（已清理多余副本）**：
- `recommend/{YYYY-MM-DD}.md` — 唯一 markdown 输出（aggregator 直接写到这里，不在日期子目录下重复写）
- scraper 输出：`2026/{MM}/{YYYY-MM-DD}/`（只放 scraper JSON + aggregated + filtered，不放 markdown）
- skill 文档：`skills/music/music-daily-recs/SKILL.md`（**不是** `skill/`、`scripts/`、`references/` 下分散的副本）
- batch 脚本：`bin/kanban-batch-scrape.py`（**不是** `scripts/` 下重复副本）

**GitHub 仓库结构（music-record repo）**：

```
music-record/
├── bin/kanban-batch-scrape.py          ← batch 脚本（唯一真源）
├── skills/music/music-daily-recs/       ← skill 文档（唯一真源）
│   └── SKILL.md
├── data/sites.json                      ← 站点配置（从 music-record 同步）
├── 2026/{MM}/{YYYY-MM-DD}/          ← 当天 scraper JSON + aggregated + filtered
└── recommend/{YYYY-MM-DD}.md            ← 唯一 markdown 输出（aggregator 直接写）
```

**五部分必须一起 push**：`bin/`、`skills/`、`data/`、`2026/`、`recommend/` 五个目录/文件每次必须同时 commit。

**repo URL**：`https://github.com/pty819/music-record`

**用户查收习惯**：上午 10 点左右看 GitHub 查收完整报告，Telegram 只收精简推送。Pipeline 凌晨 04:00 跑完，十点前结果已就绪。

### 每次 skill/py 修复后

**立即 commit 到 music-record**，下次 cron 才能拉到正确版本。不要等下次 cron 才顺手上报。

```bash
cd ~/music-record
cp ~/.local/bin/kanban-batch-scrape.py bin/
cp ~/.hermes/skills/music/music-daily-recs/SKILL.md skills/music/music-daily-recs/
git add bin/ skills/music/music-daily-recs/SKILL.md data/sites.json
git commit -m "Fix: <what you fixed>"
git push
```

## GitHub 同步（每日必须）

Pipeline 完成后的 git push 和 skill 文件管理通过 `~/music-record/` 仓库进行。

### 仓库结构

```
~/music-record/
├── bin/kanban-batch-scrape.py     ← batch 脚本
├── skills/music/music-daily-recs/  ← skill 文档（含 references/）
├── data/sites.json                ← 站点配置
├── 2026/{MM}/{YYYY-MM-DD}/   ← 当天 scraper JSON + aggregated + filtered
└── recommend/{YYYY-MM-DD}.md       ← **完整全量推荐总结**

> ⚠️ **五部分必须一起 push**：`bin/`、`skills/`、`data/`、`2026/`、`recommend/` 五个目录/文件每次必须同时 commit，不可只更新其中某一部分。

脚本同步通过 Step 1 的 `cp` 命令完成（不是 hard link）。skill 和脚本修复后必须立即 commit 到 music-record，下次 cron 才能拉到正确版本。

### Post-pipeline git push

Pipeline 完成后进入 repo push 即可（scraper 已直接写入 music-record，无需复制）：

```bash
cd ~/music-record
git add \
  bin/kanban-batch-scrape.py \
  skills/music/music-daily-recs/SKILL.md \
  "2026/$(date +%m)/$(date +%Y-%m-%d)/" \
  recommend/$(date +%Y-%m-%d).md
git commit -m "auto: $(date +%Y-%m-%d) daily recs" || exit 0
git push
```

这条命令已内置在 cron job `music-daily-recs`（ID: `6fd93b4a4c4c`）里，凌晨 04:00 自动执行。

**五部分一起 push**：`bin/`、`skills/`、`data/`、`2026/`、`recommend/` 五个目录/文件每次必须同时 commit，不可只更新其中某一部分。

## 参考文件

- `references/gateway-crash-diagnosis.md` — 05-12 cron 漏触发的根因诊断：gateway crash loop 导致 APScheduler 停止，mcp-stderr.log 重启时间线，诊断命令
- `references/aggregator-workspace-trap.md` — 2026-05-12 aggregator 读错目录的根因分析：workspace 子目录陷阱、aggregator 读到自己输出文件的路径问题、正确 aggregator body 模板
- `references/directory-migration-checklist.md` — 目录结构迁移时必查的 5 个文件 + grep 命令
- `references/musique-machine-structure.md` — 2026-05-14 Musique Machine 网站实测：页面结构、URL 模式、电影/音乐标题区分规则、常见标签
- `references/site-investigation-methodology.md` — 空 scraper 结果排查流程：RSS 验证、HTTP 状态检测、Playwright 浏览、正确 URL 定位、分类定论（2026-05-14）
- `references/scraper-diagnostics-2026-05-14.md` — 2026-05-14 全量 42 站 audit：哪些站空、为什么空、每站笔记、修复计划
- `references/template-formatting-pitfalls.md` — agg_body `%` vs f-string 格式化陷阱大全（5 种错误模式 + 综合验证流程）
- `references/minimax-thinking-leakage.md` — 2026-05-19 MiniMax M2.7 完整多段内部独白泄露的检测与修复
## 注意事项

- **workspace 必须统一**：`dir:~/music-record/2026/{MM}/{YYYY-MM-DD}/`（当天子文件夹，不是 scratch！）。scraper 各写各的 `{site_id}_reviews.json`，aggregator 读目录里所有 `*_reviews.json`，scratch 目录互相不可见。
- **并发控制**：不是 43 并行，是 **2 并行 × 22 批**。每批 2 个 task，全部 done 之后下一批才解锁（parent-gating）。这是 kanban dispatcher 对 scraper profile 的并发限制 + 进程内存限制共同决定的。
- **关于空 `score` 字段**：The Quietus、A Closer Listen 等站不给数字评分，这是正常的，不影响推荐质量。评分公式完全基于 `excerpt` 内容判断，只要 scraper 把 `excerpt` 抓完整即可。

## 维护检查清单

> **修改 skill 后必读**：`references/skill-maintenance-checklist.md` — 逐项核查路径一致性、占位符、过期标注、章节错位等常见积累性错误。

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
