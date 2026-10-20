# Site Discovery & Style Analysis Reference

## Style Distribution Analysis Methodology

When analyzing what music styles the recommendation system covers, use this approach:

### Step 1: Extract Tags from Reports
```python
import re
from collections import Counter

# Read recent reports
reports = []
for date in ['2026-06-11', '2026-06-10', ...]:
    with open(f'recommend/{date}.md', 'r') as f:
        reports.append(f.read())

# Extract all tags
all_tags = []
for report in reports:
    tag_matches = re.findall(r'\*\*标签\*\*:\s*([^\n]+)', report)
    for match in tag_matches:
        tags = re.split(r'[,/\s]+', match.strip())
        all_tags.extend([t.strip().lower() for t in tags if t.strip()])
```

### Step 2: Categorize by Style Family
Define style categories to aggregate similar tags:
- **电子**: electronic, techno, house, ambient, dub, idm, glitch, synth, ebm, electro, drone
- **实验/前卫**: experimental, avant-garde, noise, extreme, improvisation
- **爵士**: jazz, free, fusion, improv, bebop
- **摇滚**: rock, progressive, prog, psych, krautrock
- **暗潮/哥特**: darkwave, goth, post-punk, coldwave, wave, industrial
- **世界音乐**: world, folk, roots, ethnic, global, asia, african, latin
- **古典/当代**: classical, modern, contemporary, composition

### Step 3: Count and Report
```python
tag_counter = Counter(all_tags)
sorted_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)
```

### Current Style Distribution (June 2026)
Based on 5 days of reports (1038 recommendations):
1. 电子音乐: 22.1%
2. 世界音乐: 11.9%
3. 摇滚: 10.6%
4. 实验/前卫: 9.6%
5. 暗潮/哥特: 7.2%
6. 爵士: 5.5%
7. 古典/当代: 4.1%
8. 工业: 4.0%

**Gap identified**: 噪音/工业音乐 coverage is relatively weak (4.0% industrial, minimal pure noise)

---

## Site Discovery Workflow

When looking for new media sources to enrich the review library:

### 1. Web Search Strategy
Use targeted queries:
- `"experimental music" review site OR blog OR magazine`
- `noise music blog industrial music review site`
- `avant-garde music review website`
- `dark ambient blog noise industrial`

### 2. RSS Feed Validation
Check common RSS paths for each candidate site:
```python
import requests
from urllib.parse import urljoin

def check_rss(base_url):
    rss_paths = ["/feed/", "/feed", "/rss/", "/rss", "/atom.xml", "/rss.xml"]
    for path in rss_paths:
        rss_url = urljoin(base_url, path)
        try:
            response = requests.get(rss_url, timeout=5)
            if response.status_code == 200 and 'xml' in response.headers.get('content-type', ''):
                return rss_url
        except:
            continue
    return None
```

### 3. Site Evaluation Criteria
- **Update frequency**: Daily/weekly updates preferred
- **Review depth**: Full album reviews > brief mentions
- **Style focus**: Should fill gaps in current coverage
- **RSS availability**: Must have working RSS feed for automation
- **Domain authority**: Higher DA = more reliable source

### 4. 用管道真实的 feedparser 验证，不用正则判 XML

正则判定 `<?xml` / `<item` 只证明「格式像 feed」，不证明「能进管道」。最终验证必须跑管道自己在用的解析器，并断言 schema 里真实存在的字段：

```bash
python3 -c "
import feedparser, statistics
f = feedparser.parse('URL')
lens = [len(e.get('summary','')) for e in f.entries[:10]]
print(len(f.entries), '条 |',
      sum(1 for e in f.entries if e.get('title')), '有标题 |',
      int(statistics.median(lens)) if lens else 0, '中位摘要字符')"
```

⚠️ **RSS 条目 schema 里没有 `title` 字段，标题落在 `album`。** 拿 `it['title']` 断言会得到空值，看起来像抓取失败，其实是字段名不存在。

⚠️ **摘要中位长度 <400 字的 feed，先测详情页正文再下结论。** 短 feed + 长详情页（实测有 272 字 feed 对应 2.4 万字详情页）照样值得接；短 feed + 详情页也是空壳（事件列表、JS 骨架）才是真拒绝。只看 feed 摘要长度会错杀前者。

⚠️ **feed 有条目 ≠ 有乐评。** 演出日历类站（如 Bachtrack）feed 条目全是对演出排期、详情页 0 段落正文——这种接进来只会污染评分。逐条抽 2-3 条点开详情页数长 `<p>` 段落。

### 5. 候选与现有库查重（含别名）

把候选 id 与 `data/sites.json` 现有 id 对表时，**别只比完全相同的字符串**：`chain_dlk` 与 `chaindlk`、`ambient_blog` 与 `ambientblog` 这类连字符差异会把已有站当成新站报给用户。下划线/连字符两种形式都查一遍。

### 6. 产出分两级：已接入 vs 已验证待接入

调研类任务的结果在用户点头之前**不要写进 `data/sites.json`**，但验证结论必须存档在本文档里（站名、feed URL、方向、正文字数、更新频率、拒绝原因）——否则下一轮要么凭记忆重报、要么从零重测同一批死站。

---

## Verified Candidates — 已接入 sites.json（不再重复探测）

按用户兴趣方向（experimental/jazz/noise 已很密）找缺口的调研结果。全部过了第 4-5 节的 feedparser + 详情页验证，**并已全部接入 RSS 层**。缺口方向：dub techno、power electronics、当代古典、心幻/kraut。接入后 `--days 60` 实测共出货 66 条。

| Site | id | Feed | 方向 | feed 摘要 | 详情页正文 | 更新 |
|------|-----|------|------|-----------|-----------|------|
| Jazz Right Now | jazz_right_now | jazzrightnow.com/feed/ | 即兴/新爵士 | 全文级（中位 13002 字符） | — | 月更 |
| Jazz Weekly | jazzweekly | jazzweekly.com/feed/ | 爵士评论 | 873 字 | 3096 字 | 日更 |
| Aquarium Drunkard | aquarium_drunkard | aquariumdrunkard.com/feed/ | 心幻/kraut/美式 | 547 字 | 9239 字 | 日更 |
| AmbientBlog | ambient_blog | ambientblog.net/feed/ | 环境/现代作曲 | 556 字 | 1683 字 | 周更 |
| Inverted Audio | inverted_audio | inverted-audio.com/feed/ | 电子/dub techno | 272 字 | 24345 字 | 日更 |
| Noisereceptor | noise_receptor | noisereceptor.wordpress.com/feed/ | 噪音/power electronics | 全文级（892 字符） | — | 月更 |
| Freunde der Elektroakustik | fdu_de | fdu.de/feed/ | 电声/工业（德语） | 1270 字 | 1070 字 | 周更 |
| Headpress | headpress | headpress.com/feed/ | 独立出版/文化批评 | 393 字 | 1144 字 | 周更 |
| Classical Music Daily | classical_music_daily | classicalmusicdaily.com/feed.xml | 当代古典 | 135 字 | 6551 字 | 日更 |

⚠️ **月更站在生产窗口（`--days 1.5`）里必然 0 条。** 用 `--days 60` 验证它们的产出，否则会把「月更」当成「接坏了」——noise_receptor 当轮就是 `--days 60` 才看到 1 条、60 天窗口外。

⚠️ 接入后仍必须跑一次真实全量抓取确认新站有产出，不能只看 `sites.json` 字段对了就算完。

### Rejected this round (勿重复探测)

| Site | Reason |
|------|--------|
| Bachtrack | feed 是演出排期列表，详情页 0 段落正文 |
| The Playground | feed 27 条全部 0 字符正文（JS 壳） |
| PST blog | 停更于 2023-03 |
| Invisible Oranges | HTTP 403 反爬 |
| Crossing Barriers | HTTP 500 |
| MusicWeb International / Daily Bandcamp | 找不到 feed |
| Post Punk.com / Five Five Five / Salt Peanuts / Love of Music / The Urban Digest / I Care About Music | 首页不可达（DNS/超时） |
| Ben's Boring Blog / Wondering Sound / Cyclic Tangents / Six Things Music / The Eyeball Kid / Marcus Reviews / Standing on the Shoulders of Giants / Echo Park Noise | 第二轮探测：首页或 feed 全 404/超时 |
| Sounds of the Past | HTTP 200 但正文仅 1803 字节且无 item/entry 结构 |

⚠️ **两轮扫下来 26 个候选只有 9 个通过（34%）。** 下一轮仍应先查这张拒绝名单再探测，但不要因为命中率低就跳过实测——直接报“测过了能用”会骗到用户。

## Sites Added (June 2026)

After validation, 6 sites were added to the pipeline. 4 sites were rejected due to low update frequency or RSS issues.

### Added Sites

| Site | URL | RSS | Focus | Update Freq | Gap Filled |
|------|-----|-----|-------|-------------|------------|
| Noise Not Music | noisenotmusic.com | /feed/ | experimental, avant-garde, noise | 0.7/week | 噪音音乐 |
| The Noise Beneath The Snow | thenoisebeneaththesnow.wordpress.com | /feed/ | noise, gothic, industrial, metal, dark ambient | 1.0/week | 哥特/新民谣 |
| Can This Even Be Called Music? | canthisevenbecalledmusic.com | /feed/ | experimental, underground | 1.3/week | 地下音乐 |
| The Elite Extremophile | theeliteextremophile.com | /feed/ | progressive, experimental | 1.1/week | 前卫摇滚 |
| Heavy Blog Is Heavy | heavyblogisheavy.com | /feed/ | progressive, experimental, avant-garde metal | 7.5/week | 前卫金属 |
| Record Crates United | recordcratesunited.com | /feed/ | experimental, underground, cult | 1.9/week | cult音乐 |

### Rejected Sites (with reasons)

| Site | Reason |
|------|--------|
| This Is Darkness | Update frequency too low (0.2 posts/week) |
| The Road to Sound | Last updated November 2025 |
| Dungeon Synth & Dark Ambient Reviews | Last updated October 2024 |
| Louder Than War | RSS timeout, couldn't verify |

### Site Onboarding Checklist
1. ✅ Verify RSS feed works (HTTP 200 + valid XML)
2. ✅ Check update frequency (target: ≥ 0.5 posts/week)
3. ✅ Confirm review format (album reviews, not just news/playlists)
4. ✅ Add to `data/sites.json` with proper tags
5. ✅ Add to `bin/fast-rss-scrape.py` TAG_MAP
6. ✅ Update SKILL.md site list and counts
7. ✅ Git commit and push
8. ✅ Monitor first few runs for quality

---

## Pitfalls

- **Web search 只产候选名，不产结论。** 搜索结果里说的「最佳博客」多数已死；feedspot 这类聚合页比搜索引擎更值得 mining，但一切以第 4 节实测为准。
- **风格缺口先用现有库的 tags 词频定位**（`Counter` over `data/sites.json` 的 tags），拿着缺口方向去搜，比漫无目的搜「music review blog」命中率高一个量级。
- **RSS feed URLs vary**: Some use `/feed/`, others `/rss`, `/atom.xml`. Always check multiple paths.
- **WordPress sites**: Common pattern is `/feed/` endpoint
- **Content type validation**: Check response contains XML, not just 200 status
- **Update frequency matters**: Sites with < 0.5 posts/week may not be worth adding. Check the date range of recent entries.
- **RSS timeout = skip**: If RSS feed times out (> 30s), skip the site rather than trying to force it
- **Style tags inconsistency**: Different sites use different tag vocabularies. Normalize before counting.
- **TAG_MAP update required**: When adding RSS sites, must also add to `bin/fast-rss-scrape.py` TAG_MAP
- **SKILL.md counts must match**: Update all references to site counts in SKILL.md (description, architecture diagram, site list header)
- **Check content type**: Some "review" sites mainly publish news/playlists, not album reviews. Verify the site actually publishes reviews before adding.

---

## Related Skills
- `blogwatcher` - For monitoring RSS feeds (different purpose: ongoing monitoring vs. one-time discovery)
- `research` - General research methodology (too broad for this specific task)
