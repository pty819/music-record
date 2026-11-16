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

1. 只在最高档里挑（杰出 9-10）。
2. 档内按 `**风格**` 首个标签去重，保证 N 条之间风格不重叠。
3. 统计各档条数与评分分布时用 `re.findall(r'评分\*\*: (\d+)/10', txt)` 一次性拿到直方图，写进答复里的「今天有 33 张杰出」这类数字。
4. 备选组换维度：同一档里挑风格差异最大的 2-3 张，标注「换口味」而不是重复推荐。

## 交付格式要点

- 每条：`**N. 艺人 — 专辑** ｜风格标签` + 2-4 句中文简评 + 裸链接。
- 简评从报告的 `> ` 引言改写：保留乐器编制、主题、编曲手法这类信息量最高的细节，删掉「这张专辑值得一听」这类空话。
- 开头一句交代挑选口径（评分同档 + 风格不重叠），避免用户追问公平性。
- 全量清单用 GitHub 链接兜底，不要把 30+ 条全贴进微信。
