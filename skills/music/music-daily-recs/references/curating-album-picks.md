# 从日报报告里挑 N 张专辑

用于「帮我推荐 N 个专辑」这类请求：原料是当天已生成的报告，**不重新抓站、不重新评分**。

## 报告结构

`recommend/YYYY/MM/YYYY-MM-DD.md` 的结构（`## ` 分档 → `### ` 条目 → 字段行 → `> ` 引言）：

```
## 🌟 杰出 (9-10)

### La Raive — Brama
**风格**: avant-garde folk / drone / experimental / hurdy-gurdy / minimalism
**评分**: 9/10  ⭐⭐⭐⭐½
**来源**: [Songlines](https://www.songlines.co.uk/review/la-raive)
**标签**: world music
> 这张专辑在前90秒内就亮明立场：……（整段中文简评，可直接改写后交付）
```

档位标题：`## 🌟 杰出 (9-10)`、`## ⭐ 优秀 (7-8)`、`## ✅ 不错 (5-6)` 等，emoji 与文字都可能变，**按「杰出 / 优秀 / 不错 / 一般」关键词定位，不要写死 emoji**。

## 切出整个档位

读文件工具按行数分页、几百行就会被截断；杰出档常见 30+ 条 × 每条 10 行 ≈ 300+ 行。用脚本切：

```python
import re
txt = open(path, encoding="utf-8").read()
i = txt.index("## 🌟"); j = txt.index("## ⭐ 优秀")
sec = txt[i:j]
blocks = re.split(r'^### ', sec, flags=re.M)[1:]
for b in blocks:
    title = b.split("\n")[0].strip()
    style = re.search(r'\*\*风格\*\*: (.+)', b).group(1).strip()
    score = re.search(r'\*\*评分\*\*: (.+)', b).group(1).strip()
    link  = re.search(r'\*\*来源\*\*: \[(.+?)\]\((.+?)\)', b)
    quote = re.search(r'^> (.+)$', b, re.M).group(1)
```

`### ` 标题有三种形态：标准「艺人 — 专辑」、新闻稿长标题（`Artist confront X on debut album "Y"`）、纯曲名/厂牌精选名。**交付前逐条确认标题里哪个是艺人、哪个是专辑**，引言里通常能回捞艺人名。

## 挑选取样

1. 先在最高档（杰出 9-10）里挑。**最高档条数 < N 时才逐档往下补**（8/10），按「最高档优先 + 逐档补满 N」；跨档之间同样按风格错开，不要在第二档里堆同路子作者。
2. 档内按 `**风格**` 首个标签去重，保证 N 条之间风格不重叠；覆盖不足宁可换条目。
3. 统计各档条数与评分分布用脚本一次性拿直方图，写进答复里的「今天有 4 张杰出」这类数字。
4. 备选组换维度：同一档里挑风格差异最大的 2-3 张，标注「换口味」而不是重复推荐。

## 整文件解析（不依赖档位 emoji）

档位标题的 emoji 与文案会变，`txt.index("## 🌟")` 在文件结构微调后就会失效。整文件按条目切更稳，顺手拿到评分直方图：

```python
import re
from collections import Counter

txt = open(path, encoding="utf-8").read()
items = []
for b in txt.split("\n### ")[1:]:
    lines = b.split("\n")
    rest = "\n".join(lines[1:])
    def grab(pat, default=""):
        m = re.search(pat, rest, re.M)
        return m.group(1).strip() if m else default
    items.append(dict(
        title=lines[0].strip(),
        style=grab(r"\*\*风格\*\*: (.*)"),
        score=int(grab(r"\*\*评分\*\*: (\d+)/10", "0")),
        site=grab(r"\*\*来源\*\*: \[(.*?)\]"),
        url=grab(r"\*\*来源\*\*: \[.*?\]\((.*?)\)"),
        body=grab(r"^> (.*)$"),
    ))
print(Counter(i["score"] for i in items))
```

## 结构化字段查 SQLite 账本（比正则 markdown 稳）

`data/music_archive.db` 的 `appearances` 表按报告日期存了 title_raw / source / url / score / style / quote：

```bash
python3 -c "
import sqlite3
con=sqlite3.connect('file:/home/liyifan/music-record/data/music_archive.db?mode=ro',uri=True)
q='SELECT score,COUNT(*) FROM appearances WHERE date=? GROUP BY score ORDER BY score DESC'
for r in con.execute(q, ('2026-11-16',)): print(r)
q2='SELECT title_raw,source,url,score,style,quote FROM appearances WHERE date=? AND score>=? ORDER BY score DESC, style'
for r in con.execute(q2, ('2026-11-16', 8)): print(r)
"
```

`date` 列存的是报告的 UTC 日期。账本由每次 push 后的 `bin/build_archive_db.py` 重建，最新一天与磁盘报告可能差几分钟——要逐字对齐仍以报告 markdown 为准。

## 当天条目数骤减 = 跨天去重在起作用，不是站点掉链子

报告现在只收「历史账本里没有的 URL」，跨天去重会挡掉此前已推过的条目。抓 351 条、账本挡下 244 条、送评 107 条、保留 89 条是正常形态。

判据看 cron 输出的 `## Response` 段四段数（抓取总数 / 账本挡下 / 实际送评 / 评分保留）：**挡下数大而保留数小 = 去重生效**；只有「抓取总数本身骤降」才需要查站。答复里主动说清这一点，否则用户看到条数比昨天少一半会以为管道坏了。

cron 输出路径：`/root/.hermes/cron/output/a889d709f680/<YYYY-MM-DD>_<HH-MM-SS>.md` 的 `## Response` 段（永久保留，不受原始数据 3 天清理影响）。

## 交付格式要点

- 每条：`**N. 艺人 — 专辑** ｜风格标签` + 2-4 句中文简评 + 裸链接。
- 简评从报告的 `> ` 引言改写：保留乐器编制、主题、编曲手法这类信息量最高的细节，删掉「这张专辑值得一听」这类空话。
- 开头一句交代挑选口径（评分同档 + 风格不重叠），避免用户追问公平性。
- 全量清单用 GitHub 链接兜底，不要把 30+ 条全贴进微信。
