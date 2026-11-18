# 跨天去重：根因、量化配方与「仓里有多少专辑」的口径

适用于两类问题：**「日报里怎么有这么多重复？」** 和 **「这个仓一共多少张专辑？」**。两者问的是同一份数据的不同切面。

## 两层去重，只有一层存在

| 层 | 实现 | 跨天去重 |
|---|---|---|
| RSS（60 站） | `fast-rss-scrape.py` | ✅ 按 GUID 的增量去重 |
| HTML（17 脚本） | `scrape_html_parallel.py` | ❌ **只有当天内部去重** |

HTML 站抓的是站点「最新乐评」列表页，一篇乐评在列表上停留几天/几周，就会**每天被重新收进当天日报**。所以重复**只可能来自 HTML 层**，RSS 层是干净的。

判定重复来源时看 `**来源**` 站点分布：少数几个列表型 HTML 站会贡献绝大部分重复条目。

## 重复的形态与它为什么会被掩盖

- 同一篇乐评在多份日报里以**同一个 URL** 出现（正文可能略有差异）。
- **标题整行去重会把重复率低估**：同一篇文章在不同站/不同日子，标题可能带大小写或归一化差异（`RootsWorld` vs `roots_world`），所以「唯一标题数」永远大于「唯一 URL 数」。
- 列表型 HTML 站还会产出占位标题（如「未知专辑」）——那不是重复，是**标题解析失败**被兜底了，看到成百上千条同名占位要先查解析而不是查去重。

## 量化配方（先量，再定性）

```python
import re, glob, collections
files = sorted(glob.glob('/home/liyifan/music-record/recommend/**/*.md', recursive=True))
occ = collections.defaultdict(list)
for f in files:
    date = re.search(r'(\d{4}-\d{2}-\d{2})\.md$', f).group(1)
    txt = open(f, encoding='utf-8').read()
    for b in re.split(r'^### ', txt, flags=re.M)[1:]:
        t = b.split('\n')[0].strip()
        if not t:
            continue
        m = re.search(r'\*\*来源\*\*: \[(.+?)\]', b)
        occ[re.sub(r'\s+', ' ', t)].append((date, m.group(1) if m else '?'))
dist = collections.Counter(len(v) for v in occ.values())
print('出现次数分布:', dict(sorted(dist.items())))
for t, v in sorted(occ.items(), key=lambda kv: -len(kv[1]))[:10]:
    print(len(v), t[:60], '跨', len({d for d, _ in v}), '天')
```

看两件事：**分布是否两极分化**（大量只出现 1-2 次 = 正常跨站覆盖；一小撮出现几十上百次 = 跨天重复），以及**重复条目的站点分布**（是否集中在几个 HTML 列表站）。

## 「仓里一共多少专辑」= 三种口径，数字差一个数量级

必须先说清用的哪个键，否则数字无法互相校验：

| 口径 | 键 | 典型量级 | 说明 |
|---|---|---|---|
| 归档条目总数 | 无（原始行数） | 数万条 | 含重复 |
| 唯一**标题** | `### ` 标题整行归一化 | 约为条目数的 40% | 同 URL 不同写法的标题会各算一张 |
| 唯一**专辑**（DB） | `data/music_archive.db` 的 `albums` 表行数 | 与唯一标题同量级 | 账本去重后的权威数 |
| 「专辑 — 艺人」格式条目 | 标题匹配「艺人 — 专辑」 | 唯一标题的 1/3 左右 | **只统计标准命名格式的条目**，专题/年度清单/电台混录/访谈不在内 |

```bash
python3 -c "
import sqlite3
con=sqlite3.connect('file:/home/liyifan/music-record/data/music_archive.db?mode=ro',uri=True)
print('albums 表:', con.execute('SELECT COUNT(*) FROM albums').fetchone()[0])
print('appearances 表:', con.execute('SELECT COUNT(*) FROM appearances').fetchone()[0])
print('meta:', dict(con.execute('SELECT key,value FROM meta')))
"
```

**汇报纪律：报任何「多少张专辑」都要同时报去重键和一条查询语句。** 用户会追问口径，答不出键的口径数字会被当成误报。

## 现在管道已接历史账本

历史去重账本（`data/music_archive.db` 的 `appearances.url`）已接入出货管道：全量路径与增量路径都会先把**账本里已有的 URL** 挡掉，不评分、不入账。所以：

- **新报告不再产生跨天重复**。
- **历史报告不回溯改写**——归档里已有的重复仍然在（这是历史事实，改写等于重写成品）。
- 报告条目数从三百降到几十，通常是账本在挡，不是站点掉链子（判据见 `references/curating-album-picks.md`）。

## 边角与坑

- **账本重建**：每次 push 后跑 `bin/build_archive_db.py`；账本与磁盘报告可能差几分钟，逐字对齐以 markdown 为准。
- **DB 缺失/读失败时过滤自动失效**（退化为原行为），所以「突然全是重复」要先确认账本文件存在且可读，再怀疑站点。
- **占位标题（解析失败）不是重复**；混在重复分析里会得出错误结论。
- **来源站名要归一化**再统计：`RootsWorld`/`roots_world`、`Songlines`/`songlines` 视为同一站，否则站点分布会骗人。
