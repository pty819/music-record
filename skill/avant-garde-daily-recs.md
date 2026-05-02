---
name: avant-garde-daily-recs
description: 每日巡检前卫/实验/学院派爵士/电子/世界音乐评论站，输出结构化专辑推荐清单。RSS 优先，Playwright 保底，web_search 跨站补充。全量写入 GitHub 仓库，Telegram 只推送 top 20。
category: music
tags: [experimental, jazz, electronic, world-music, avant-garde, music-reviews, synthwave, darksynth, dungeon-synth, dark-ambient]
author: hermes-agent
version: 1.1
created: 2026-04-20
updated: 2026-05-03
trigger_condition: 每天北京时间凌晨 03:00 自动触发，或手动调用

> ## ⚠️ 执行策略（2026-05-03 重大更新：并发 subagent 方案已验证）
>
> **2026-05-03 实测有效：5 个 subagent 并发巡检，30 张候选，推荐质量显著提升。**
>
> **推荐的新执行流程（必须优先使用）：**
>
> 1. **并发 subagent 巡检**：`delegate_task(tasks=[...])` 一次最多 3 个并发，多批执行。每 agent 独立巡检 3-4 个站点，互不干扰。
> 2. **主 session 只负责汇总**：收集各 subagent 的 JSON 结果，合并去重，生成 markdown，推送 GitHub + Telegram。
> 3. **nohup 仍用于 cron 场景**：cron 触发 → skill 立即返回 → nohup 进程后台跑 → 下次 cron 检测结果文件。
> 4. **Playwright 降级规则不变**：browser_navigate 超时 → 立即改用 web_search。
> 5. **web_search 是 paywall 站唯一途径**：The Quietus / A Closer Listen / Bandcamp Daily 等直接抓取无效，必须 web_search 跨站。
output_target: Telegram（top 20 主推荐）/ GitHub（全量 markdown）
---

# Avant-Garde Daily Recs Skill

## 用途

每天自动浏览音乐评论网站，筛选符合口味的专辑，输出"今日专辑推荐清单"到 Telegram。

## 核心执行逻辑（必须按顺序执行）

```
Step 1: 读取本 skill 的站点配置表（sites.json）
Step 2: 构建今日待巡检队列（根据各站 crawl_frequency）
Step 3: 对每个站点：
    ├─ 优先检查是否有 RSS URL
    │   ├─ 有 RSS → 用 feedparser / curl 抓 RSS，解析条目
    │   └─ 无 RSS → 用 Playwright headless + stealth 模式抓页面
    │       └─ 导航到 Reviews/Albums/分类栏目
    │       └─ 提取文章标题/URL/日期/标签
    │       └─ 若检测到 Cloudflare JS 挑战（"Just a moment..."）→ 降级 headed 模式
Step 4: 对每个候选页面：
    ├─ 读取正文（RSS 条目摘要 或 Playwright 抓正文）
    ├─ 判断是否符合口味
    └─ 打分（见评分公式）
Step 5: 过滤 + 去重
Step 6: 生成主推荐 + 候选补充
Step 7: 输出 Markdown + JSON
Step 8: 推送到 Telegram Home Channel（**top 20 主推荐**，精简格式）
Step 9: **关闭所有 Playwright 浏览器进程**（browser_navigate("about:blank") + kill 残留 chromium）
```

## 站点配置表

### S 级站点（每天巡检）

| 站点名 | 主页 | RSS URL | 评论栏目URL | 分类标签 | 备注 |
|---|---|---|---|---|---|
| The Wire | https://www.thewire.co.uk/ | ❌ 无效 | https://www.thewire.co.uk/category/reviews | experimental, avant-garde, sound art | RSS 返回 HTML 而非 XML；paywall 无法绕过；用 web_search 跨站搜索 |
| The Quietus | https://thequietus.com/ | ⚠️ paywall | https://thequietus.com/columns/quietus-reviews/ | experimental, electronic, jazz, world | RSS 摘要 <150字符即截断；跨站搜索是唯一途径 |
| A Closer Listen | https://acloserlisten.com/ | ⚠️ 部分可用 | https://acloserlisten.com/ | experimental, ambient, drone, modern composition | Cloudflare JS 挑战拦截 curl/Playwright；正文需通过 web_search 跨站获取 |
| Avant Music News | https://avantmusicnews.com/ | ✅ 可用（受限） | https://avantmusicnews.com/ | experimental, avant-garde, progressive | 高频更新；Dusted Reviews / Jazzword Reviews roundup 含实际专辑评论 |
| Bandcamp Daily | https://daily.bandcamp.com/ | ⚠️ 部分可用 | https://daily.bandcamp.com/ | experimental, electronic, world | 站方拦截直接 HTTP；Album of the Day 模式可用 curl 抓取；Essential Releases 需 web_search |
| Boomkat | https://boomkat.com/ | ❌ 无RSS | https://boomkat.com/ | experimental, electronic, noise | ASN 黑名单，整个 IP 段被禁；跳过 |
| Igloo Magazine | https://igloomag.com/ | ✅ 可用 | https://igloomag.com/feed/ | experimental electronic, IDM, ambient | |
| Fluid Radio | https://www.fluid-radio.co.uk/ | ❌ 被污染 | https://www.fluid-radio.co.uk/ | drone, ambient, electroacoustic | RSS 被西班牙语博彩内容污染；跳过 |
| DownBeat | https://downbeat.com/ | ❌ 无效 | https://downbeat.com/ | jazz, modern jazz | RSS 内容质量低；跳过 RSS，直接 web_search |
| All About Jazz | https://www.allaboutjazz.com/ | ❌ 无效 | https://www.allaboutjazz.com/ | jazz, avant-jazz, fusion | RSS 无有效专辑乐评；跳过 RSS，直接 web_search |
| Free Jazz Blog | https://www.freejazzblog.org/ | ✅ 可用 | https://www.freejazzblog.org/ | free jazz, avant-jazz | Blogger 平台，域名重定向至 The Free Jazz Collective |
| I CARE IF YOU LISTEN | https://icareifyoulisten.com/ | ✅ 可用 | https://icareifyoulisten.com/ | contemporary classical, new music | |
| Songlines | https://www.songlines.co.uk/ | ❌ 无RSS | https://www.songlines.co.uk/category/reviews | world music, folk | 订阅墙；Playwright 仅见标题+图片；用 web_search |
| Resident Advisor | https://ra.co/ | ⚠️ XML 错误 | https://ra.co/reviews | electronic, club, experimental | RSS namespace 冲突导致解析失败；用 web_search |
| The Dungeon In Deep Space | https://thedungeonindeepspace.com/ | ✅ 最可靠 | https://thedungeonindeepspace.com/ | dungeon synth, dark ambient | web_extract 始终可达；dungeon synth / dark ambient 垂直度最高 |

### A 级站点（隔天或每周 2-3 次）

| 站点名 | 主页 | RSS URL | 评论栏目URL | 分类标签 | 备注 |
|---|---|---|---|---|---|
| Noise Not Music | https://noisenotmusic.com/ | https://noisenotmusic.com/feed | https://noisenotmusic.com/ | experimental, improvised, noise | verified_open; experimental/improvised/noise 边界专辑评论 |
| Cyclic Defrost | https://www.cyclicdefrost.com/ | ❌ 无RSS | https://www.cyclicdefrost.com/ | experimental, innovative, ambient | verified_open; 澳大利亚方向，补 ambient/electronics/modern composition 边界 |
| Jazz Right Now | https://www.jazzrightnow.com/ | https://www.jazzrightnow.com/feed | https://www.jazzrightnow.com/category/album-reviews/ | improvised, experimental, creative music | verified_open; avant-jazz 与 creative music 主源 |
| Vehlinggo | https://vehlinggo.com/ | https://vehlinggo.com/feed | https://vehlinggo.com/category/synthwave-dot-net/synthwave-reviews/ | synthwave, retrowave, darksynth | verified_open; synthwave/retrowave/soundtrack-adjacent 评论 |
| NewRetroWave | https://newretrowave.com/ | https://newretrowave.com/feed | https://newretrowave.com/category/music/album-reviews/ | synthwave, darksynth, retrowave | verified_open; synthwave/darksynth/retrowave 核心媒体 |
| Electrozombies | https://electrozombies.com/ | https://electrozombies.com/feed | https://electrozombies.com/music/review/ | synthwave, darkwave, darksynth | verified_open; 覆盖 darksynth/synthwave 支线 |
| This Is Darkness | https://www.thisisdarkness.com/ | https://www.thisisdarkness.com/feed | https://www.thisisdarkness.com/tag/dungeon-synth/ | dark ambient, dungeon synth | verified_open; dark ambient 核心源，兼顾 dungeon synth |
| Dungeon Synth & Dark Ambient Reviews!! | https://thedungeonindeepspace.com/ | https://thedungeonindeepspace.com/feed | https://thedungeonindeepspace.com/category/dungeon-synth/ | dungeon synth, dark ambient | verified_open; dungeon synth / dark ambient 垂直度最高的评论源 |

### B 级站点（每周 1-2 次）

| 站点名 | 主页 | RSS URL | 评论栏目URL | 分类标签 |
|---|---|---|---|---|
| Textura | https://www.textura.org/ | https://www.textura.org/feed/ | https://www.textura.org/ | jazz, ambient, experimental |
| Point of Departure | https://www.pointofdeparture.org/ | https://www.pointofdeparture.org/feed/ | https://www.pointofdeparture.org/journal/ | improvised music, creative music |
| The Squid's Ear | https://www.squidco.com/ear/ | https://www.squidco.com/ear/feed/ | https://www.squidco.com/ear/ | jazz, experimental, electroacoustic |
| JazzTimes | https://www.jazztimes.com/ | https://www.jazztimes.com/feed/ | https://www.jazztimes.com/ | jazz, reviews |
| Sequenza21 | https://www.sequenza21.com/ | https://www.sequenza21.com/feed/ | https://www.sequenza21.com/ | contemporary classical |
| VAN Magazine | https://van-magazine.com/ | ❌ 无RSS | https://van-magazine.com/ | classical, contemporary |
| World Music Central | https://worldmusiccentral.org/ | https://worldmusiccentral.org/feed | https://worldmusiccentral.org/ | world music, fusion |
| Rhythm Passport | https://rhythmpassport.com/ | https://rhythmpassport.com/feed/ | https://rhythmpassport.com/ | world music, roots |
| ProgArchives | https://www.progarchives.com/ | https://www.progarchives.com/rss.xml | https://www.progarchives.com/ | progressive rock, fusion |
| Sea of Tranquility | https://www.seaoftranquility.org/ | ❌ 无RSS | https://www.seaoftranquility.org/category/reviews | prog, fusion |
| The Rest Is Noise PH | https://therestisnoiseph.com/ | ❌ 无RSS | https://therestisnoiseph.com/ | asian, experimental |
| Mixmag Asia | https://mixmag.asia/ | ❌ 无RSS | https://mixmag.asia/category/reviews | asian electronic, ambient |
| Syrphe | https://syrphe.com/ | ❌ 无RSS | https://syrphe.com/ | african, asian, experimental |

### B 级站点（每周 1-2 次）

| 站点名 | 主页 | RSS URL | 备注 |
|---|---|---|---|
| ATTN:Magazine | https://www.attnmagazine.co.uk/ | https://www.attnmagazine.co.uk/feed/ | experimental, longform |
| The Chain D.L.K. | https://www.chaindlk.com/ | https://www.chaindlk.com/feed/ | dark ambient, industrial |
| Musique Machine | https://www.musiquemachine.com/ | ❌ 无RSS | 用 Playwright |
| HHV Mag | https://www.hhv-mag.com/ | https://www.hhv-mag.com/feed/ | electronic, vinyl culture |
| A Strangely Isolated Place | https://www.astrangelyisolatedplace.com/ | https://www.astrangelyisolatedplace.com/feed/ | ambient, modern classical |
| New Music Buff | https://newmusicbuff.com/ | https://newmusicbuff.com/feed/ | electroacoustic, new music |
| JazzTrail | https://jazztrail.net/ | https://jazztrail.net/feed/ | avant jazz |
| Truth & Lies Music | https://www.truthandliesmusic.com/ | ❌ 无RSS | free jazz |
| Jazz Journal | https://jazzjournal.co.uk/ | ❌ 无RSS | 老牌 jazz |
| 5:4 | https://5against4.com/ | https://5against4.com/feed/ | modern classical |
| Modern Classical Music | https://www.modernclassicalmusic.com/ | https://www.modernclassicalmusic.com/feed/ | modern classical |
| The Classic Review | https://theclassicreview.com/ | ❌ 无RSS | classical, contemporary |
| fRoots | https://frootsmag.com/ | https://frootsmag.com/feed/ | folk, roots |
| RootsWorld | https://www.rootsworld.com/ | https://www.rootsworld.com/feed/ | world music |
| ProgressoR | https://www.progressor.net/ | ❌ 无RSS | art-rock, prog |
| Prog Mistress | https://progmistress.com/ | ❌ 无RSS | prog |
| Wild City | https://www.thewildcity.com/ | ❌ 无RSS | south asian, electronic | |
| Bandwagon Asia | https://www.bandwagon.asia/ | https://www.bandwagon.asia/feed/ | asian music | |
| Hear65 | https://hear65.bandwagon.asia/ | ❌ 无RSS | singapore music | |

### 补充源（fallback_only / discovery_only，不主导日常结果）

| 站点名 | 主页 | RSS URL | 评论栏目URL | 分类标签 | automationStatus |
|---|---|---|---|---|---|
| Spectrum Culture | https://spectrumculture.com/ | https://spectrumculture.com/feed | https://spectrumculture.com/category/music/ | experimental, jazz, electronic, world | fallback_only |
| Synth Digest | https://www.synthdigest.com/ | https://www.synthdigest.com/feed | https://www.synthdigest.com/ | dungeon synth, synth | fallback_only |
| fromheretillnow | https://www.fromheretillnow.com/ | ❌ 无RSS | https://www.fromheretillnow.com/ | discovery, curated | discovery_only |
| Invisible Oranges | https://www.invisibleoranges.com/ | https://www.invisibleoranges.com/feed | https://www.invisibleoranges.com/ | dungeon synth, metal-adjacent | discovery_only |

## RSS 抓取规则

### 为什么要优先用 RSS
- 结构化数据，不需要解析 HTML
- 绕过多数 bot 检测
- 速度快，资源消耗低
- 内容质量由编辑筛选过一次

### RSS 抓取步骤

1. **获取 RSS**：用 `curl -L -H "User-Agent: Mozilla/5.0" {rss_url}` 抓原始 XML
2. **解析**：用 Python 标准库 `xml.etree.ElementTree`（不要用 feedparser，hermes-agent venv 里没有）
3. **过滤日期**：只保留最近 7 天内更新的条目（避免重复推荐老内容）
4. **提取字段**：
   - `entry.title` → 标题（需解析出"专辑名 — 艺人名"格式）
   - `entry.link` → 文章 URL
   - `entry.summary` / `entry.description` → 摘要（正文预览）
   - `entry.published_parsed` → 发布日期
5. **判断是否适合推荐**：
   - 有专辑名 + 艺人名
   - 摘要中包含实验/爵士/电子/世界音乐等关键词
   - 不是纯粹新闻稿（摘要长度 > 100 字符）
6. **RSS 摘要 < 150 字符时 / 被 paywall / Cloudflare 拦截**：
   - **不降级 Playwright**（绕不过订阅墙）
   - **必须用 `web_search` 跨站搜索** — 搜 `"album_name artist_name review"` 在其他评论站找实质内容
   - 优先找 Bandcamp Daily、The Quietus、Boomkat、A Closer Listen、SaitenKult 等正文可达的站
   - 搜索到的内容补充到推荐原因和备注里
   - **即使搜索结果不理想，条目仍然写入 markdown**（备注标注"搜索补充"或"全文未获取"），不丢弃任何候选
   - The Quietus Reviews 栏目页除外——其页面本身已渲染专辑名+摘要，可以直接在列表页打分

### RSS 关键词过滤（命中以下任意一个则进入候选）

**高相关（进入优先候选）：**
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

**降权/排除（遇见了扣分或直接跳过）：**
- pop, mainstream, singer-songwriter（除非有实验性标签）
- EDM, trance（除非有 experimental 前缀）
- 仅含 "review" 但无实质内容的短讯

## Playwright 执行规则（无 RSS 时启用）

### 默认模式：headless + stealth

**必须安装的包（使用 uv）：**
```bash
uv pip install feedparser --python ~/.hermes/hermes-agent/venv/bin/python3
cd ~/.hermes/hermes-agent
npm install playwright-extra puppeteer-extra-plugin-stealth
```

**默认配置：**
- `headless: true`（Playwright `--headless=new`，Chrome 112+，和真实 Chrome 共用代码库）
- 注入 `playwright-extra` + `puppeteer-extra-plugin-stealth`（隐藏 `navigator.webdriver` 等指纹）
- User-Agent：`Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36`
- viewport：`1920x1080`，locale：`en-US`
- 页面超时：30 秒

### 降级 headed 的唯一触发条件

检测到 Cloudflare JS 挑战（页面标题或 body 包含 "Just a moment..."、"Performing security verification" 或 "Ray ID"）→ 切换：

- `headless: false` + `xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24"`
- 等待时间延长到 15 秒
- 降级后仍需注入 stealth 插件

### 问题站点处理

**跳过（headless 或 headed 都无法访问）：**

| 站点 | 原因 |
|---|---|
| Boomkat | ASN 黑名单，整个 IP 段被禁 |
| Syrphe | ERR_CONNECTION_CLOSED，网站不稳定 |
| Textura | JS 渲染空白，headless/headed 均无效 |

**预判需要降级 headed：**

| 站点 | 原因 |
|---|---|
| ProgArchives | Cloudflare JS 挑战 |

任何站点出现 "Just a moment..." 提示均按上述方式降级。

### 浏览器清理（强制，每次都必须执行）

1. 抓完目标页面 → 用 `browser_navigate("about:blank")` 关闭当前页面
2. 检查残留进程：`ps aux | grep -E 'chromium|chrome' | grep -v grep`
3. 如有残留：`kill $(pgrep -f -E 'chromium|chrome')`
4. **绝对不能**在不关闭浏览器的情况下直接退出 skill 流程

### 站点访问步骤（通用模板）

```
1. 打开站点主页
2. 等待网络空闲（networkidle）
3. 截图保存到 /tmp/recs/{site_name}_{date}.png
4. 查找 Reviews / Albums / Features 导航入口
5. 进入 Reviews 列表页
6. 提取所有文章卡片：
   - 文章标题 <h3> 或 <h2>
   - 文章链接 <a href>
   - 发布日期
   - 分类标签
7. 对每张文章卡片：
   - 提取摘要文字（hover 或直接可见）
   - 判断是否涉及目标类型
   - 如果是，跳转正文页抓完整内容
8. 提取正文后打分
```

### Playwright 站点异常 Fallback

| 异常情况 | 处理方式 |
|---|---|
| 页面 JS 重，无法立即抓 | `page.wait_for_load_state('networkidle')`，最多等 15s |
| 页面内容为空 | 用 `page.content()` 取原始 HTML，看是否需要登录 |
| 被 403/403 | 换 User-Agent，缩短等待时间，或标记为"需要手动处理" |
| RSS 摘要太短（< 200字符） | 降级到 Playwright 抓正文 |
| 当天无更新 | 回看最近 7 天内的条目 |

## 评分公式

对每个候选专辑打分，只推荐总分 >= 9 的进入主推荐。

```
total_score = critic_quality(0-5) + taste_match(0-5) + novelty(0-3) + cross_domain_bonus(0-3) + regional_bonus(0-2) - mainstream_penalty(0-3)
```

### 各维度说明

**critic_quality (0-5)**
- 5：真正的乐评，正文具体提到编制/音色/结构/文化背景
- 4：有实质性评论，包含流派标签和描述
- 3：一般乐评，有基本信息
- 2：摘要短讯，无正文
- 1：只有标题和一句话
- 0：新闻稿/公告/票务

**taste_match (0-5)**
- 5：同时命中多个口味维度（如 free jazz + electroacoustic + world fusion）
- 4：明确属于前卫/实验/avant-jazz/学院派电子等核心方向
- 3：相关但偏 adjacent（如 indie rock adjacent to experimental）
- 2：边缘相关（如 mainstream jazz with some experimental elements）
- 1：擦边球
- 0：完全不符合

#### Synthwave / Darksynth / Dungeon Synth / Dark Ambient 追加加权（叠加到 taste_match 基础分）

在 taste_match 基础分之上，按以下关键词命中情况追加加权：

| 命中类型 | 关键词 | 追加加权 |
|---|---|---|
| synthwave 类 | synthwave, retrowave, outrun | +1 |
| darksynth 类 | darksynth, horror synth, cyberpunk synth | +2 |
| dungeon synth / fantasy 类 | dungeon synth, fantasy synth, medieval ambient | +2 |
| dark ambient 类 | dark ambient, ritual ambient, neoclassical dark ambient | +2 |
| cinematic / soundtrack 类 | soundtrack-inspired, cinematic synth, atmospheric synth | +1 |
| Berlin school / kosmische | berlin school, kosmische, kosmische musik | +1 |

**跨子类叠加**：若同时命中两个以上不同子类（例如 synthwave + darksynth，或 dungeon synth + dark ambient），额外 +1。

**跨域交叉**（见 cross_domain_bonus 扩展规则）。

**novelty (0-3)**
- 3：全新概念/跨文化方法/unusual instrumentation/地区首发
- 2：有明显创新元素
- 1：有新意但不突出
- 0：无新意

#### Synthwave / Darksynth / Dungeon Synth / Dark Ambient 追加加权（叠加到 novelty 基础分）

| 情况 | 条件 | 追加加权 |
|---|---|---|
| synth/darksynth + world/folk/ritual 元素结合 | 正文或标签明确提到 | +2 |
| dungeon synth + 现代 sound design / electroacoustic / field recording | 正文或标签明确提到 | +2 |
| 非纯 nostalgia 模仿，在叙事/世界观/音色设计有明显扩展 | 评论明确强调 | +1 |
| 评论强调 "textural", "cinematic", "worldbuilding", "ritualistic", "atmospheric" 且有细节支撑 | 非空话 | +1 |

**cross_domain_bonus (0-3)**
- 3：横跨 3 个以上口味维度（如 free jazz + electronics + world music）
- 2：横跨 2 个维度
- 1：跨 1 个维度
- 0：单一维度

#### Synthwave / Darksynth / Dungeon Synth / Dark Ambient 追加交叉规则

| 交叉组合 | 追加加权 |
|---|---|
| synthwave/darksynth + experimental electronic | +2 |
| darksynth + industrial / ritual / horror ambient | +2 |
| dungeon synth + dark ambient | +2 |
| dungeon synth + folk / medieval / world elements | +2 |
| dark ambient + electroacoustic / sound art | +2 |
| synth music + prog / fusion / jazz-rock | +2 |
| 同时横跨三类（例如 dark ambient + ritual electronics + world/folk） | 再 +1 |

**regional_bonus (0-2)**
- 2：涉及东南亚/南岛/中亚/拉丁美洲/非洲等少见地区 scene
- 1：有地域特色但非核心
- 0：欧美主流

**mainstream_penalty (0-3)**
- 3：纯流行、无实验性的 mainstream indie
- 2：有实验标签但内容空洞
- 1：偏主流但有可取之处
- 0：不属于 mainstream penalty 范围

#### Synthwave / Retrowave / Dungeon Synth / Dark Ambient 降权规则（补充）

**Synthwave / Retrowave 降权：**
- 只有 80s nostalgia aesthetic，没有明显声音创新：`-1`
- 更接近普通 pop / synthpop 单曲，而不是专辑级作品：`-1`
- 评论语言只是在说 "fun", "nostalgic", "retro vibes"，没有结构/音色/叙事细节：`-1`
- 纯霓虹封面 + 常规鼓机 + 常规 lead synth，没有 dark / cinematic / compositional 特征：`-1`

**Dungeon Synth / Dark Ambient 降权：**
- 只是低保真循环 pad 堆叠，没有明显叙事感、音色设计或世界构建：`-1`
- 纯 tape-noise / lo-fi texture，但评论里没有给出细节支撑：`-1`
- 更像 demo / sketch / scene ephemera，而不是完成度高的专辑：`-1`

### 评分通过阈值（无数量上限）
- **主推荐**：总分 >= 9，**全部写入 markdown，不设上限**
- **候选补充**：总分 6-8，**全部写入 markdown，不设上限**
- **不推荐**：总分 < 6，写入"全部候选表"备注栏

> **数量说明**：每天爬几十到上百个站点候选，所有评分 >= 6 的条目全部落盘。不再限定"8张主推荐 + 8张候选补充"。

## 推荐多样性规则（参考性，不再硬性限制）

以下类型分布作为每日结构参考，**不作为筛选条件**，符合评分的条目全部保留：

| 类型 | 参考占比 |
|---|---|
| 实验/电子（experimental, electronic, IDM, glitch） | 20-30% |
| avant-jazz / improvised music | 15-25% |
| world fusion / roots hybrid | 10-15% |
| modern classical / electroacoustic | 10-15% |
| prog/fusion / avant-rock | 5-10% |
| synthwave / darksynth / retrowave | 10-15% |
| dungeon synth / dark ambient / fantasy synth | 10-15% |

**去重规则：**
- 同一专辑被多站写到：保留评论最具体的那篇作为主来源，其他仅记录在备注
- 连续三天内不要被同一批网站主导（手动调整权重）
- 如果当天高质量内容不足（< 8 张主推荐），回看最近 7 天内容，但标注"非当天首发"

### Markdown（完整版，写入 GitHub 仓库）

**GitHub 仓库全量版**：包含所有候选条目（评分 >= 6），格式如下：

```markdown
今日专辑推荐清单（YYYY-MM-DD）
更新时间：HH:MM 北京时间
数据来源：X 个站 | Y 篇候选

## 主推荐（top 20，按评分排序）

1. **专辑名** — [艺人名](https://example.com)
   类型：`类型标签`
   推荐原因：一句具体的话，说明为什么值得听
   来源：[站点名](https://site.com) | [文章标题](https://article.com)
   评分：N

## 候选补充（评分 6-8，全量写入）

1. **专辑名** — [艺人名](https://example.com)
   类型：`类型标签`
   推荐原因：一句话
   来源：[站点名](https://site.com) | [文章标题](https://article.com)
   评分：N

## 今日全部候选（按评分排序）

| # | 专辑 | 艺人 | 来源 | 类型 | 评分 | 备注 |
|---|---|---|---|---|---|---|
| 1 | Album | Artist | Site | Type | 18 | 主推荐 |
...

---
数据采集：RSS（X站） + Playwright（Y站） | 评分公式见 Skill
```

> **Telegram 推送版**：只取前 20 条主推荐（评分最高的 20 条），精简格式（无全部候选表），推送到 Home Channel。
>
> **GitHub 仓库版**：全量 markdown，包含所有评分 >= 6 的条目 + 全部候选表。
>
> **JSON 版**保存在本地 `~/.hermes/cron/output/daily_album_recs_{YYYY_MM_DD}.json`，不推送。

## 推荐原因写法规范（强制执行）

**好例子（原有方向）：**
- 把自由爵士管乐、粗粝电子纹理和近乎仪式性的打击循环缝在一起，张力非常足。
- 在南岛/东南亚打击乐语感上叠加氛围电子与现场采样，既有地景感也有现代制作感。
- 用室内乐式写法处理 drone 和 electroacoustic 材料，整体非常克制但细节密度很高。
- 在 jazz-rock 框架里加入合成器噪点和前卫编曲，听感接近 fusion 与 avant-prog 的交叉地带。

**好例子（Synthwave / Darksynth / Retrowave）：**
- 在合成器驱动的复古框架里加入更阴暗的音色设计和电影化推进，不只是怀旧，而是有完整叙事感的电子专辑。
- 用 darksynth / horror-synth 的重型音色和明确的专辑结构把复古合成器语言推向更强的戏剧张力。
- 把 retrowave 的可听性和更实验的声音层次缝在一起，既有钩子也有足够细节。

**好例子（Dungeon Synth / Dark Ambient）：**
- 以 dungeon synth 的世界构建感为基础，把 dark ambient 的空间感和质感细节做得很完整。
- 不是单纯的 lo-fi fantasy 氛围堆叠，而是有明确场景感、叙事感和声音层次的 dark ambient / dungeon synth 作品。
- 把仪式感、黑暗氛围和 fantasy-adjacent 合成器写法结合起来，整体沉浸感非常强。

**好例子（跨界型）：**
- 把 synth music 的电影化推进和实验电子/暗氛围材料结合起来，落在类型边界上而不是纯粹复古模仿。
- 在黑暗合成器和环境音响设计之间找到平衡，既有类型辨识度，也有超出圈层公式化写法的细节。

**差例子（直接降分）：**
- "很好听"
- "口碑不错"
- "值得一听"
- "很前卫"
## ⚠️ 输出规范：完整候选记录（强制执行）

**Markdown 是主要输出载体**，不再只输出最终筛选的 16 条。Markdown 必须包含**所有经过评分的候选专辑**，即使不入选最终主推荐/候选补充也要落盘。

**Markdown 结构：**
```markdown
今日专辑推荐清单（YYYY-MM-DD）
更新时间：HH:MM 北京时间
数据来源：X 个站 | Y 篇候选

## 主推荐

1. **专辑名** — [艺人名](https://example.com)
   类型：`类型标签`
   推荐原因：一句话（基于实际评论内容）
   来源：[站点名](https://site.com) | [文章标题](https://article.com)
   评分：N

## 候选补充

1. **专辑名** — [艺人名](https://example.com)
   类型：`类型标签`
   推荐原因：一句话
   来源：[站点名](https://site.com) | [文章标题](https://article.com)
   评分：N

## 今日全部候选（按评分排序）

| # | 专辑 | 艺人 | 来源 | 类型 | 评分 | 备注 |
|---|------|------|------|------|------|------|
| 1 | Album | Artist | Site | Type | 18 | 主推荐 |
| 2 | Album | Artist | Site | Type | 15 | 候选补充 |
| 3 | Album | Artist | Site | Type | 14 | 全文未获取，paywall站 |
...
```

**"全部候选"节要求：**
- 包含今日所有经过评分（>= 6 分）的候选专辑
- 按评分从高到低排序
- 每行：`# | 专辑 | 艺人 | 来源 | 类型 | 评分 | 备注`
- 备注列：注明是否主推荐/候选补充，或"全文未获取"（paywall 站且 cross-site 搜索无结果）
- paywall 站（The Wire 等）且 cross-site 搜索后仍无实质内容的，**全文未获取的标注"全文未获取"**，不入主推荐/候选补充，但仍在全部候选表里
- 这个表是给人类审核用的，不需要写推荐原因，只要客观信息

**JSON 版用途：**
- cron job 之间的状态传递和程序读取
- 记录**所有评分 >= 6 的条目**（不限于 16 条）
- JSON 不再推送给用户，用户只看 Markdown

## ⚠️ 重要架构说明：并发 subagent 执行方案（2026-05-03 验证）

**结论：必须用 `delegate_task(tasks=[...])` 的 batch 模式并发执行，不要用 nohup 方案替代并发采集。**

### 关键限制（需注意）

1. **`delegate_task(tasks=[...])` 一次最多 3 个并发**（`max_concurrent_children=3`），超过会报错。超过 3 个任务时分多批调用。
2. **subagent 是完全隔离的**：没有共享内存，每个 agent 独立工作，主 session 只负责汇总结果。
3. **cron 场景仍需 nohup**：cron 触发后 skill 必须立即返回才能不被 kill，并发 subagent 在 cron 模式下不适用。cron 场景用 nohup 把完整采集丢后台，主 session 快速返回。

### 手动执行（推荐）：并发 subagent 巡检流程

```
Step 1: 加载 skill，理解站点配置（sites.json）
Step 2: 把站点按类型分成 3-5 组，每组 3-4 个站点（RSS可靠的、paywall需web_search的、爵士专项等）
Step 3: 调用 delegate_task(tasks=[...]) 并发执行，主 session 等待所有 subagent 返回
Step 4: 收集各 subagent 的 JSON 结果，合并去重
Step 5: 生成 markdown，写入 GitHub repo
Step 6: 推送 Telegram（top 20 主推荐）
```

### cron 执行（nohup 方案）

```
Step 1: cron 触发 skill
Step 2: skill 立即 fork: terminal(command="nohup python3 /path/to/crawler.py > /tmp/crawler.log 2>&1 &", background=false)
Step 3: skill 立即返回 SUCCESS
Step 4: nohup 进程独立运行
Step 5: 下一次 cron（比如 03:30）检测 ~/.hermes/cron/output/daily_album_recs_{date}.json 是否存在
Step 6: 存在则推送 Telegram
```

**注意**：cron 场景下，如果任务量可控（≤8 个 RSS 站），可以直接在 skill 里用 Python 并发跑完，不需要 nohup。

## 每日 cron job 配置

> 注意：cron job 已通过 `cronjob` 工具创建（job_id: `575adedce803`），触发时间为北京时间每天 `0 3 * * *`（凌晨 03:00）。此节仅供参考，不要重复创建。

```yaml
name: avant-garde-daily-recs
trigger: "0 3 * * *"  # 每天北京时间 03:00
deliver: telegram
model:
  provider: minimax-cn
  model: MiniMax-M2.7
skills:
  - avant-garde-daily-recs
```

## 执行前检查清单

每次 cron 触发前，agent 应确认：
- [ ] 各站点 URL 可达（RSS 能抓 + 页面能开）
- [ ] 当前日期用于文件名和标题
- [ ] 输出路径：`~/.hermes/cron/output/daily_album_recs_{date}.md`
- [ ] Telegram deliver target 已配置

## 常见陷阱与处理

1. **The Quietus 正文中间插 newsletter block**：用正则跳过 "Don't miss The Quietus Digest" 段落
2. **Bandcamp Daily 场景报道含多张专辑**：解析时将文章正文分段，每段对应一张专辑
3. **RSS 摘要太短（< 150字符）或 paywall 站**：不降级 Playwright（绕不过订阅墙），改用 `web_search` 跨站搜索专辑在其他站是否有实质评论。无实质内容则不进主推荐
4. **Cloudflare JS 挑战**：页面出现 "Just a moment..." → 降级 headed 模式（见 Playwright 执行规则节）
5. **Boomkat / Syrphe / Textura**：已知无法访问，跳过（详见 Playwright 执行规则节的问题站点处理表）
6. **同一天同一站多篇相关文章**：最多取前 5 篇，避免被单一站点主导
7. **评分全是边界值（8-9）**：如果主推荐 < 6 张，候选补充放宽到 12 张
8. **Playwright 超时**：单站超时 60s 后直接跳过，继续下一个站
9. **Playwright 浏览器残留**：每次任务结束必须关闭浏览器（见 Playwright 执行规则节的浏览器清理节）
10. **RSS 摘要含 HTML 标签**：The Wire、The Quietus 等 WordPress/RSS 源的 summary 字段常含 `<img>`、`<p>` 等 HTML 标签，解析前需用 `re.sub(r'<[^>]+>', '', summary)` strip 掉再打分
11. **Resident Advisor RSS 解析失败**：RA 的 RSS (`https://ra.co/feed/news`) 含有 XML namespace 冲突导致 `xml.etree.ElementTree` 报 "unbound prefix"，遇到此错误应跳过该站并在日志标记
12. **DownBeat / All About Jazz 无有效 RSS**：两个站的 RSS URL 在 sites.json 中已标为 `has_rss: false`，不要尝试抓 RSS，直接用 Playwright
13. **Free Jazz Blog 重定向**：实际域名为 `freejazzblog.org`，但首页展示为 "The Free Jazz Collective"，使用 Blogger 平台，Playwright 列表页可直接提取文章标题和摘要
14. **Songlines 订阅墙**：首页 reviews-hub 是搜索数据库，Playwright 可见的专辑卡片仅含标题+图片，无摘要文字，需点击进入详情页才能抓描述

## GitHub 仓库管理

### 仓库初始化（只需执行一次）

```bash
# 确认 gh 已登录
gh auth status

# 创建公开仓库
gh repo create 音乐推荐 --public --description "每日音乐推荐清单，前卫/实验/学院派爵士/电子/世界音乐" --clone false

# 或如果仓库已存在，直接克隆
gh repo clone pty819/音乐推荐 ~/.hermes/music-recs-repo 2>/dev/null || true
```

**仓库路径**：`~/.hermes/music-recs-repo`

### 每日 GitHub 推送流程（每次 cron 执行）

```
Step 1: 生成当日 markdown 文件
Step 2: 写入本地仓库对应年-月目录
Step 3: git add + commit + push
Step 4: 验证 push 成功
```

#### 文件路径规则

```
~/.hermes/music-recs-repo/
└── {YYYY}/
    └── {MM}/
        └── {YYYY-MM-DD}.md   # 例如 2026/04/2026-04-29.md
```

#### 推送命令（Python subprocess）

```python
import subprocess
import os
from datetime import datetime

REPO_PATH = os.path.expanduser("~/.hermes/music-recs-repo")
DATE = datetime.now().strftime("%Y-%m-%d")
YEAR = datetime.now().strftime("%Y")
MONTH = datetime.now().strftime("%m")
DATE_MD = f"{DATE}.md"

# 确保目录存在
dir_path = os.path.join(REPO_PATH, YEAR, MONTH)
os.makedirs(dir_path, exist_ok=True)

# 读取当日 markdown 内容
md_path = os.path.join(dir_path, DATE_MD)
# md_content 在前面步骤已生成

with open(md_path, "w", encoding="utf-8") as f:
    f.write(md_content)

# git add / commit / push
cmds = [
    ["git", "-C", REPO_PATH, "add", "."],
    ["git", "-C", REPO_PATH, "commit", "-m", f"docs: add {DATE} music recommendations"],
    ["git", "-C", REPO_PATH, "push", "origin", "main"],
]
for cmd in cmds:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"WARNING: git command failed: {' '.join(cmd)}")
        print(result.stderr)
```

### 首次仓库初始化（Python）

```python
import subprocess
import os

REPO_PATH = os.path.expanduser("~/.hermes/music-recs-repo")
SKILL_PATH = os.path.expanduser("~/.hermes/skills/avant-garde-daily-recs")

# 如果仓库不存在，创建并克隆
result = subprocess.run(
    ["gh", "repo", "create", "music-record", "--public",
     "--description", "每日音乐推荐清单，前卫/实验/学院派爵士/电子/世界音乐",
     "--clone"],
    capture_output=True, text=True,
    cwd=os.path.dirname(REPO_PATH)
)
if result.returncode != 0 and "already exists" not in result.stderr:
    print(f"Repo creation: {result.stderr}")
else:
    subprocess.run(
        ["gh", "repo", "clone", "pty819/music-record", REPO_PATH],
        capture_output=True
    )

# 初始化 git config
if os.path.exists(os.path.join(REPO_PATH, ".git")):
    subprocess.run(["git", "-C", REPO_PATH, "config", "user.name", "hermes-agent"], check=False)
    subprocess.run(["git", "-C", REPO_PATH, "config", "user.email", "hermes@local"], check=False)

# 建立 skill 目录的 hard link（指向本地 skill，inode 相同，编辑自动同步）
os.makedirs(os.path.join(REPO_PATH, "skill", "references"), exist_ok=True)
subprocess.run(["ln", "-f",
    os.path.join(SKILL_PATH, "SKILL.md"),
    os.path.join(REPO_PATH, "skill", "avant-garde-daily-recs.md")], check=False)
subprocess.run(["ln", "-f",
    os.path.join(SKILL_PATH, "references", "sites.json"),
    os.path.join(REPO_PATH, "skill", "references", "sites.json")], check=False)
subprocess.run(["ln", "-f",
    os.path.join(SKILL_PATH, "references", "quick-ref.md"),
    os.path.join(REPO_PATH, "skill", "references", "quick-ref.md")], check=False)
```

> **注意**：使用 hard link（inode 相同）而非 symlink。同一文件系统内，编辑 skill 文件后 repo 内对应文件自动同步，无需重新 ln。GitHub push 时会推送实际内容而非路径。同一文件系统的判定：`df` 两个路径返回相同挂载点即可用 hard link。

### ⚠️ 重要：两套输出规范

**Telegram**：只推送 top 20 主推荐（评分最高的 20 条），精简格式，无全部候选表。

**GitHub 仓库**：全量 markdown，评分 >= 6 的条目全部写入，包含"今日全部候选表"。

```markdown
| # | 专辑 | 艺人 | 来源 | 类型 | 评分 | 备注 |
|---|---|---|---|---|---|---|
| 1 | Album | Artist | Site | Type | 18 | 主推荐 |
| 2 | Album | Artist | Site | Type | 15 | 候选补充 |
| 3 | Album | Artist | Site | Type | 12 | 全文未获取，paywall站 |
| 4 | Album | Artist | Site | Type | 12 | 搜索补充 |
...
```

**备注规则**：
- `主推荐` — 总分 >= 9，进入最终推荐
- `候选补充` — 总分 6-8，进入候选补充
- `全文未获取` — paywall 站且 cross-site 搜索无实质结果
- `搜索补充` — paywall/cloudflare 站，跨站搜索后补充了信息
- `非当天首发` — 回看 7 天内内容
- `评分<6` — 不推荐，但仍在全部候选表里供人工参考

这样即使是几十条甚至上百条记录，都会完整保存到仓库里。

---

## ⚠️ 实测 RSS / 站点有效性总结（2026-04-29 更新）

以下为实测结果，巡检策略必须以此为准：

| 站点 | RSS 实际可用性 | 实测问题 |
|---|---|---|
| The Dungeon In Deep Space | ✅ **最可靠** | `web_extract` 始终可访问，dungeon synth / dark ambient 垂直度最高的评论源 |
| Avant Music News | ✅ 可用（受限） | 主要内容为演出日历；Dusted Reviews / Jazzword Reviews roundup 含实际专辑评论，从中提取专辑名 |
| SaitenKult | ✅ 可用 | 可直接 `curl` 抓取正文，评论质量高 |
| Igloo Magazine | ✅ 可用 | RSS 可解析，正文质量高 |
| I CARE IF YOU LISTEN | ✅ 可用 | RSS 可解析 |
| Free Jazz Blog | ✅ 可用 | Blogger 平台，域名重定向至 The Free Jazz Collective |
| The Wire | ❌ 无效 | 返回 HTML 而非 XML，feed 内容几乎全为 playlists/interviews，专辑乐评极少 |
| The Quietus | ⚠️ paywall | RSS 有内容但 paywall，摘要 <150字符即截断，跨站搜索是唯一途径 |
| A Closer Listen | ⚠️ 被拦截 | Cloudflare JS 挑战拦截 curl 和 Playwright；用 `web_search` 跨站搜索 |
| Bandcamp Daily | ⚠️ 被拦截 | 站方拦截直接 HTTP，Playwright 也返回 challenge page；用 `web_search` 搜索专辑名 |
| Fluid Radio | ❌ 被污染 | RSS 被西班牙语博彩内容污染，无法使用 |
| DownBeat | ❌ 无效 | RSS 内容质量低；跳过 RSS，直接 web_search |
| All About Jazz | ❌ 无效 | RSS 无有效专辑乐评；跳过 RSS，直接 web_search |
| Songlines | ❌ 被墙 | 订阅墙，Playwright 仅见标题+图片；用 web_search |
| Resident Advisor | ❌ XML 错误 | RSS namespace 冲突导致 xml.etree.ElementTree 解析失败；用 web_search |

**实测结论（2026-04-29）**：
- **最可靠的获取路径**：`web_extract` thedungeonindeepspace.com（dungeon synth/dark ambient） + `web_search` 跨站找其他评论站的实质内容
- **web_search 是主力获取工具** — 大多数站（The Quietus、A Closer Listen、Bandcamp Daily、Songlines 等）都无法直接抓取正文，跨站搜索是获取实质评论的最可靠路径
- **AMN roundup 提取**：AMN 的 Dusted Reviews / Jazzword Reviews 段落包含多个专辑名，从中提取作为候选，再用 `web_search` 找详情
- **SaitenKult** 是少数可以直接 curl 完整抓取正文的评论站，可作为 free jazz / avant-garde 的可靠来源
- **execute_code 写文件时注意**：Python f-string 里不能用未转义的单引号；用双引号或先赋值变量再格式化

### 执行前检查清单

每次 cron 触发前，agent 应确认：
- [ ] sites.json 路径正确（技能加载后用 `os.path.expanduser('~/.hermes/skills/avant-garde-daily-recs/references/sites.json')` 展开 home 目录，而非 hardcode `/root/...`）
- [ ] 各站点 URL 可达（RSS 能抓 + 页面能开）
- [ ] 当前日期用于文件名和标题
- [ ] 输出路径：`~/.hermes/cron/output/daily_album_recs_{date}.md`
- [ ] Telegram deliver target 已配置

### 实测：The Wire 的 RSS 根本无法用于乐评内容提取

The Wire 的 RSS（`https://www.thewire.co.uk/feed`）只包含标题和极短摘要，没有乐评正文。其订阅墙（paywall）也无法通过 Playwright 绕过。

**正确 workflow（已验证）：**
1. 从 RSS 匹配到标题（如 "Unlimited Editions: Hive Mind"）
2. **不降级 Playwright**（无效）
3. 改用 `web_search` 跨站搜索：`"Hive Mind" "Unlimited Editions" review`
4. 在 Bandcamp Daily、The Quietus、Boomkat、A Closer Listen 等正文可达的站找实质内容
5. 搜索后仍无实质内容的条目 → **不进主推荐**，在 JSON 里标注 `"note": "paywall站原文未获取，仅标题命中"`

**教训：** 不能用评分维度描述（regional_bonus、taste_match 词汇）充当推荐原因。推荐原因必须基于实际获取到的评论正文生成，哪怕只有一段话。

### sites.json 实际路径（非 hardcode）
在 cron 环境（hermes-agent venv）中，`~/.hermes/...` 展开为 `/home/liyifan/.hermes/...`，而非 `/root/.hermes/...`。

**正确路径**：
```python
sites_path = '/home/liyifan/.hermes/skills/avant-garde-daily-recs/references/sites.json'
```
不要 hardcode `/root/...`，始终用 `os.path.expanduser('~')` 或完整路径。

### execute_code 写文件时的 Python f-string 陷阱

Python f-string 里不能嵌套未转义的单引号。错误写法：
```python
reason = '布里斯班的噪音项目，带有 glorious 的描述'  # 单引号内嵌在 f-string 里会报 SyntaxError
md += f"推荐原因：{reason}"
```
正确写法：
```python
reason = "布里斯班的噪音项目，带有 glorious 的描述"  # 用双引号包裹含单引号的字符串
md += f"推荐原因：{reason}"
```
**教训**：所有含内嵌单引号的字符串在 f-string 里使用时必须用双引号包裹。

### RSS 源内容质量差异（2026-04-25 实测）
| 站点 | RSS 内容 | 问题 |
|---|---|---|
| The Wire | 91 条/天 | 主要是 playlists/interviews/columns，专辑乐评少 |
| The Quietus | 32 条/天 | 有 `quietus-reviews` URL 模式，专辑乐评占比高 |
| A Closer Listen | 8 条/天 | WordPress，专辑名—艺人名 格式清晰 |
| Bandcamp Daily | 38 条/天 | 场景报道为主，专辑需正文解析 |

**建议**：The Wire RSS 需二次过滤（`is_album_review()` + URL pattern `/reviews/` 或标题含 `reviewed`）。

### The Wire 过滤规则（强制执行）

The Wire RSS **几乎不产出专辑乐评**，全是 playlists / interviews / columns / 年终总结。必须二次过滤后才能参与评分。

**判断逻辑**（`is_album_review_wire()` 必须同时满足）：

1. 摘要里没有 `playlist` / `to accompany his article` / `to accompany his report` / `compiles an annotated playlist` / `explores a playlist` 等引导语
2. 标题格式含"艺人名: 专辑名"或"艺人名 — 专辑名"（不是纯主题词）

**硬过滤**（以下情况直接 skip，不参与评分，不记入 source_limits）：
- 摘要含 "playlist" → 不是专辑乐评
- 摘要含 "to accompany his article/report" → 不是专辑乐评
- 标题无冒号/破折号分隔艺人名和专辑名 → 不是专辑乐评格式

```python
THE_WIRE_PLAYLIST_PATTERNS = [
    "to accompany his article",
    "to accompany his report",
    "to accompany her article",
    "compiles an annotated playlist",
    "explores a playlist",
    "playlist of tracks",
]

def is_album_review_wire(title, summary):
    """The Wire 专用：判断是否是专辑乐评而非 playlist/feature"""
    s = (title + " " + summary).lower()
    for pat in THE_WIRE_PLAYLIST_PATTERNS:
        if pat in s:
            return False
    # 标题必须有艺人:专辑格式（含冒号/破折号）
    if not (":" in title or "–" in title or " - " in title):
        return False
    return True
```

**Source Diversity 规则**：
1. `MAX_PER_SOURCE = 3` — 每源最多 3 条主推荐
2. The Wire 经 `is_album_review_wire()` 过滤后仍满足条件的条目，才能参与评分和 source_limits 计数

### sites.json has_rss 字段校验（部分不准确）
以下站点标了 has_rss=true 但实际需用 Playwright：
- DownBeat (`downbeat.com/rss.xml`) — 内容质量低
- All About Jazz (`allaboutjazz.com/rss.xml`) — 无有效专辑乐评

建议实际执行时对这两个站直接跳过 RSS，用 Playwright 抓 Reviews 栏目。

### RSS 内容质量实测（2026-04-25）

| 站点 | RSS 实际内容 | 问题 |
|---|---|---|
| The Wire | 91条/天 | 几乎全是 playlists/interviews/columns，专辑乐评极少（<5%），无法用于主推荐 |
| The Quietus | 32条/天 | 专辑乐评占比高但 paywall，RSS 摘要 <150字符即正文已截断，Playwright 也无法绕过订阅墙 |
| A Closer Listen | 8条/天 | WordPress，专辑名—艺人名格式清晰，**正文可直接 curl 抓取** |
| Bandcamp Daily | 38条/天 | Essential Releases 需 JS 渲染；**Album of the Day 可直接 curl 抓取正文** |
| Avant Music News | 20条/天 | 主要内容为演出日历；**Dusted Reviews / Jazzword Reviews roundup 含实际专辑评论** |
| Fluid Radio | 10条/天 | RSS 被西班牙语博彩内容污染，无法使用 |

### 实测有效的降级 workflow

1. **RSS 摘要 <150字符 + The Quietus/The Wire 等已知 paywall 站**：
   - 不降级 Playwright（绕不过订阅墙）
   - 改用 `web_search` 跨站搜索专辑评论
   - 搜索无实质结果 → 进入"全文未获取"状态，不进主推荐

2. **A Closer Listen**：
   - URL 含 `/2026/` 日期即为专辑评论页
   - `curl` 直接抓页面即可获取完整正文

3. **Bandcamp Daily Album of the Day**：
   - 模式：`/album-of-the-day/{album-slug}-review`
   - `curl` 页面可获取完整评论正文（<100KB 的页面含完整内容）

4. **Avant Music News roundups**：
   - `Dusted Reviews` 和 `Jazzword Reviews` 栏目标注了实际专辑评论
   - 从 roundup 摘要中提取专辑名/艺人名作为候选
   - 跨站搜索获取评论详情

### 教训：不能用评分维度描述充当推荐原因

The Wire RSS 匹配到 "Unlimited Editions: Hive Mind" 时，得分高（因为 gamelan/world 相关关键词命中），但 RSS 摘要本身只是 "To accompany his article..." 这类引导文字，没有乐评正文。

### 付费墙 / 搜索补充流程（强制执行，不得跳过）

当遇到以下情况时，**必须**按顺序执行：

1. **检测到 paywall / 摘要 < 150 字符 / 提示 "to accompany his article" 等引导语**
2. **先用 `is_album_review_wire()` 做 The Wire 专用判断**（见上节）
3. **通过 The Wire 判断后**，对于任何站点的 paywall 条目：
   - 用 `web_search("\"{album_name}\" \"{artist_name}\" review site:bandcampdaily.com OR site:thequietus.com OR site:acloserlisten.com OR site:saitenkult.de OR site:boomkat.com OR site:textura.org")` 搜索其他站的评论
   - 优先找 Bandcamp Daily、The Quietus、A Closer Listen、SaitenKult、Boomkat、Textura 等正文可达的站
4. **搜索到实质内容** → 用实际评论内容生成推荐语，进入候选
5. **搜索后仍无实质内容** → 标注 `"全文未获取，仅搜索补充"` 后可进入候选（评分 >= 9 才进主推荐，否则进候选补充），**不得自行脑补推荐语**

**禁止的行为**：
- 不得用评分维度描述（"张力非常足""值得反复聆听"）充当推荐语
- 不得在搜索失败后直接跳过
- 不得用 "全文未获取" 作为不进候选的借口——只要搜索了、评分够了，就必须进候选表

```python
def supplement_review_via_search(title, summary, artist=None, album=None):
    """跨站搜索补充推荐语"""
    # 先解析出 album 和 artist（从 title 格式 "Album — Artist" 或 "Artist: Album"）
    query = f'"{album}" "{artist}" review' if album and artist else f'"{title}" review'
    search_results = web_search(query, limit=5)
    # 找正文可达的站的评论
    for result in search_results.get('data', {}).get('web', []):
        url = result['url']
        if any(site in url for site in ['bandcampdaily.com', 'thequietus.com', 'acloserlisten.com',
                                          'saitenkult.de', 'boomkat.com', 'textura.org',
                                          'quietus.com', 'acl.to']):
            content = web_extract([url])
            if content and len(content) > 200:
                return content  # 返回实际评论正文用于生成推荐语
    return None
```

## 执行环境注意事项（2026-04-22 实测）

### 文件访问
- `execute_code` 沙盒以 `liyifan` 用户运行，而 cron 输出目录属于 `root`，导致 PermissionError
- 解决方案：用 `terminal()` (subprocess.run curl) 而非 `read_file` / `execute_code` 写文件；或确保输出目录权限为 755
- sites.json 是 `{"sites": [...]}` 结构，需用 `data['sites']` 而非直接迭代 data

### RSS 解析已知失败站（xml.etree.ElementTree 无法处理）
| 站点 | 错误类型 | 处理 |
|---|---|---|
| Resident Advisor (`ra.co/feed/news`) | "unbound prefix" - XML namespace 冲突 | 跳过，记录日志 |
| Point of Departure | "undefined entity &rsquo;" - HTML 实体未声明 | 跳过，记录日志 |
| The Squid's Ear | "not well-formed (invalid token)" | 跳过，记录日志 |

这三个站遇到解析错误时直接跳过，不要尝试修复 XML。
