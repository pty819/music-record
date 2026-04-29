# Avant-Garde Daily Recs — 执行快速参考

> 本文件是 SKILL.md 的执行摘要，完整文档见 SKILL.md。

## 执行优先级规则

| Tier | 频率 | 触发条件 |
|---|---|---|
| S 级 | 每天 | 全部 14 个站 |
| A 级 | 隔天 | `day % 2 == 0`（按日期奇偶轮询） |
| B 级 | 每周 2 次 | 周五 + 周一（dow >= 4 or dow <= 0）|

**S 级站点（14 个）：**
`the_quietus`, `a_closer_listen`, `avant_music_news`, `bandcamp_daily`, `igloo_magazine`, `fluid_radio`, `downbeat`, `all_about_jazz`, `free_jazz_blog`, `icareifyoulisten`, `resident_advisor`, `the_wire`, `boomkat`, `songlines`

**A 级站点（13 个，按日轮询）：**
`textura`, `point_of_departure`, `squids_ear`, `jazztimes`, `sequenza21`, `van_magazine`, `world_music_central`, `rhythm_passport`, `progarchives`, `sea_of_tranquility`, `rest_is_noise_ph`, `mixmag_asia`, `syrphe`

**B 级站点（19 个，周五+周一）：**
`attn_magazine`, `chain_dlk`, `musique_machine`, `hhv_mag`, `strangely_isolated_place`, `new_music_buff`, `jazz_trail`, `truth_and_lies_music`, `jazz_journal`, `five_against_four`, `modern_classical_music`, `the_classic_review`, `froots`, `roots_world`, `progressor`, `prog_mistress`, `wild_city`, `bandwagon_asia`, `hear65`

---

## RSS 源速查表（21 个有效 RSS）

### 实验 / 电子 / 氛围 / 声响艺术（8 个）

| 站点 | RSS URL | 备注 |
|---|---|---|
| The Wire | https://www.thewire.co.uk/feed | 英国前卫/实验核心 |
| The Quietus | https://thequietus.com/feed | 英国实验/电子/跨界 |
| Avant Music News | https://avantmusicnews.com/feed/ | 高频新专辑发现 |
| Bandcamp Daily | https://daily.bandcamp.com/feed | 编辑选品/场景报道 |
| Fluid Radio | https://www.fluid-radio.co.uk/feed/ | 声景/氛围/电声 |
| The Chain D.L.K. | https://www.chaindlk.com/feed/ | 地下边缘电子 |
| HHV Mag | https://www.hhv-mag.com/feed/ | 电子/黑胶文化 |
| A Strangely Isolated Place | https://www.astrangelyisolatedplace.com/feed/ | 后氛围/现代古典 |

### 爵士 / 即兴 / 自由爵士（4 个）

| 站点 | RSS URL | 备注 |
|---|---|---|
| Point of Departure | https://pointofdeparture.org/?feed=rss2 | 高质量长文/creative music |
| The Squid's Ear | https://www.squidco.com/ear/feed/ | 即兴/爵士/实验交叉 |
| JazzTimes | https://www.jazztimes.com/feed/ | 现代爵士/学院派 |
| JazzTrail | https://jazztrail.net/feed/ | avant jazz 补充 |

### 当代古典 / 现代作曲（4 个）

| 站点 | RSS URL | 备注 |
|---|---|---|
| I CARE IF YOU LISTEN | https://icareifyoulisten.com/feed/ | 美国当代作曲入口 |
| Sequenza21 | https://www.sequenza21.com/feed/ | 新音乐社区 |
| 5:4 | https://5against4.com/feed/ | 现代古典/实验 |
| Modern Classical Music | https://www.modernclassicalmusic.com/feed/ | 直给型现代古典 |

### 世界音乐 / roots（4 个）

| 站点 | RSS URL | 备注 |
|---|---|---|
| World Music Central | https://worldmusiccentral.org/feed/ | 全球 roots/融合 |
| Rhythm Passport | https://rhythmpassport.com/feed/ | 世界融合/现场 |
| fRoots | https://frootsmag.com/feed/ | folk/roots 历史 |
| RootsWorld | https://www.rootsworld.com/feed/ | world music 脉络 |

### 其他 / 补充（4 个）

| 站点 | RSS URL | 备注 |
|---|---|---|
| ATTN:Magazine | https://www.attnmagazine.co.uk/feed/ | 实验长文/声艺 |
| Resident Advisor | https://ra.co/feed/news | 电子/club/亚洲场景 |
| New Music Buff | https://newmusicbuff.com/feed/ | 当代作曲/电声 |
| A Closer Listen | https://acloserlisten.com/feed/ | 实验/器乐/氛围 |

---

## 无 RSS 必须 Playwright 的站（共 25 个）

### 已知问题站（跳过）

| 站点 | 原因 |
|---|---|
| Boomkat | ASN 黑名单，整个 IP 段被禁 |
| Syrphe | ERR_CONNECTION_CLOSED，网站不稳定 |
| Textura | JS 渲染空白，headless/headed 均无效 |

### 默认 headless+stealth（21 个）

`downbeat`, `all_about_jazz`, `free_jazz_blog`, `igloo_magazine`, `songlines`, `van_magazine`, `sea_of_tranquility`, `rest_is_noise_ph`, `mixmag_asia`, `strangely_isolated_place`, `roots_world`, `jazz_trail`, `bandwagon_asia`, `wild_city`, `musique_machine`, `the_classic_review`, `truth_and_lies_music`, `progressor`, `prog_mistress`, `hear65`, `jazz_journal`

### 预判需降级 headed（1 个）

| 站点 | 原因 |
|---|---|
| ProgArchives | Cloudflare JS 挑战 |

---

## RSS 解析（重要：不要用 feedparser）

**hermes-agent venv 没有 pip，也没有 feedparser 模块。**

必须用 Python 标准库：
```python
from xml.etree import ElementTree as ET
from urllib.request import urlopen, Request

req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urlopen(req, timeout=15) as resp:
    root = ET.fromstring(resp.read())

# RSS 2.0
for item in root.find("channel").findall("item"):
    title = item.find("title").text.strip()
    link  = item.find("link").text.strip()
    desc  = (item.find("description") or item.find("summary") or _empty_elem).text or ""

# Atom
for entry in root.iter():
    if entry.tag.endswith("}entry") or entry.tag == "entry":
        ...
```

**RSS 内容质量的根本问题**：80%+ 的 RSS 条目是新闻/采访/专栏，不是专辑乐评。摘要本身往往无法判断质量。**正确流程**：
1. 先用 RSS 筛出候选文章（按关键词）
2. 对候选文章 follow link，用 Playwright 或 curl 抓正文
3. 读完正文再打分

## 执行流程（快速对照）

> ⚠️ 注意：hermes-agent venv 没有 feedparser。必须用 `xml.etree.ElementTree` + `urllib` 标准库解析 RSS，不要尝试安装 feedparser。

```
Step 1: 读取 sites.json
Step 2: 按日期计算今日 tier（S 每天 + A/B 按频率）
Step 3: 对每个站点：
    has_rss=true → 标准库 XML 解析 RSS（不要用 feedparser）
                   → follow 候选文章 link 抓正文
                   → 读完正文再打分
    has_rss=false → Playwright headless+stealth（默认）
                   检测 CF JS 挑战 → 降级 headed + xvfb
Step 4: 评分（total >= 9 进主推荐）
Step 5: 去重 + 多样性检查
Step 6: 输出 Markdown + JSON 到 ~/.hermes/cron/output/
Step 7: 关闭浏览器（browser_navigate("about:blank") + kill chromium）
Step 8: 推送 Telegram Home Channel
```

**cron 护栏**：subagent 3 分钟无输出会被调度系统打断。如果任务量太大，先分批做，或者每批输出一个中间文件再继续。

## 评分公式

```
total = critic_quality(0-5) + taste_match(0-5) + novelty(0-3)
       + cross_domain(0-3) + regional(0-2) - mainstream(0-3)
>= 9：主推荐
6-8：候选补充
< 6：不推荐
```

## 推荐原因写法

✅ 把自由爵士管乐、粗粝电子纹理和近乎仪式性的打击循环缝在一起，张力非常足。
✅ 在南岛/东南亚打击乐语感上叠加氛围电子与现场采样，既有地景感也有现代制作感。
❌ 很好听。很值得一听。很前卫。口碑不错。
