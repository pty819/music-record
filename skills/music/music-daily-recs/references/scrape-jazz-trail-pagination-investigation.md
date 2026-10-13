# jazz_trail 翻页慢 诊断实录 (2026-06-09)

> **当用户问"为什么 X 站 3 分钟都搞不定"或"卡在哪"时的标准诊断方法。**
> 适用于任何 scrape_*.py 报"慢"/"卡"/"超时"但又**没明确错误**的情况。

## 1. 结论先行（先看这）

**j-t 不是 hang，是结构性慢**：

| 指标 | 数字 |
|---|---|
| 实际跑完耗时 | **252s**（360s timeout 留 108s 余量） |
| 翻页总数 | **86 页**（offset 2026-04 → 2016-06） |
| 单页 fetch 耗时 | 1.8-3.0s，**curl 健康** |
| in-window 页面 | **1 页**（page 1，1 条 review） |
| 0 new reviews 的页 | 85/86 = **99%** |
| last offset → 日期 | `1489677786543` = 2017-03-16 |
| 真正翻完的日期 | 2016-06-07（j-t blog 起点，`get_next_page_url` 返回 None） |

**根因**：`scrape_jazz_trail.py:204` `while next_url:` 主循环**只依赖 `older-posts` 链接是否存在**。j-t 站点自 2009 起累计数千篇 blog，offset 翻页机制下**永远有"older-posts"**，必须翻到 2016-06 blog 起点才停。

**SKILL.md 旧注释"j-t 翻页多但 --days 1.5 会正确过滤"——错的**：`--days 1.5` 只过滤**单页内**的 item，**不**停止翻页本身。`scrape_sea_of_tranquility.py` 那种"5 条连续 < cutoff 早停"机制在 j-t 里**根本不存在**。

**为什么 6-01~6-07 cron 都"成功"了**（mtime 显示 9-10 分钟跑完）——当时**没有 180s wrapper timeout**。旧 SKILL.md 把 scrape 直接放后台，没设上限。6-09 c7d149c 升级加了 180s wrapper timeout，j-t 跑 252s 就被砍了——**3 分钟超时 = 砍在 page 75+**。

## 2. 诊断方法（class-level，可复用）

**核心原则**：用户说"卡"≠ 真 hang。先证明是 hang / 慢 / 网络 / 数据 三种之一，再修。

### 步骤 1: 拷脚本到 /tmp 加 stderr 计时，**不改主逻辑**

```bash
cp ~/music-record/bin/scrape_X.py /tmp/x_diag.py
```

加 `import time as _t`，**module-level** 设 `_T0 = 0.0`（不能在 main() 里赋值，f-string 会触发 UnboundLocalError），main() 开头赋值 `_T0 = _t.monotonic()`。

**`sys.stderr.write(f"[T+{int((_t.monotonic()-_T0)*10)/10}s] ...")`** 给所有日志加时间戳。fetch 函数加 START/DONE 时间戳 + URL + 字节数。

⚠️ **不要改业务逻辑**——只加计时。否则诊断失败的话业务逻辑也乱了。

### 步骤 2: 拉到 timeout 360s 跑一次

```bash
START=$(date +%s)
timeout 360 python3 /tmp/x_diag.py --days 1.5 > /tmp/x_diag_out.json 2> /tmp/x_diag.log
echo "RC=$? ELAPSED=$(($(date +%s)-START))s"
```

**360s** 而不是 180s——要给"它真的能跑完"留余地。如果是死循环会 360s 被砍；如果是慢会跑完 rc=0。

### 步骤 3: log 抽 4 个数

```bash
# 1. 总翻页数
grep -c "Page " /tmp/x_diag.log

# 2. 唯一 offset 数（vs 总数 = 有无重复）
grep -oE "offset=[0-9]+" /tmp/x_diag.log | sort -u | wc -l

# 3. 哪些页有 new reviews
grep -E "Page [0-9]+: [1-9][0-9]* new" /tmp/x_diag.log

# 4. last offset → 日期
LAST=$(grep -oE "offset=[0-9]+" /tmp/x_diag.log | tail -1 | cut -d= -f2)
python3 -c "from datetime import datetime, timezone; print(datetime.fromtimestamp(int('$LAST')/1000, tz=timezone.utc))"
```

### 步骤 4: 算"in-window 命中率"

```
in-window pages = grep -c "Page .*: [1-9] new"
total pages = grep -c "Page "
ratio = in-window / total
```

| ratio | 含义 | 修法 |
|---|---|---|
| < 5% | 翻页**严重过剩**（j-t = 1/86 = 1.2%） | 加早停（连续 N 页 0 new break） |
| 5-30% | 翻页**略多** | 加"page 1 后若无 new 停" 之类弱早停 |
| 30-70% | 翻页**合理** | 不是翻页问题，看 fetch / parse |
| > 70% | 翻页**不够** | 改 `while` 条件或加 `MAX_PAGES` |

**j-t 1.2% = 早停缺失，根因在主循环**。

## 3. 修复方案（待用户确认后 commit）

`scrape_jazz_trail.py` main() 加 1 个早停字段：

```python
empty_pages = 0
while next_url:
    ...
    if new_count == 0:
        empty_pages += 1
        if empty_pages >= 2:  # 保守：2 页 0 new = 停
            break
    else:
        empty_pages = 0
```

**两种风格**：
- **A 保守（empty_pages ≥ 2）**：j-t 8s 内完成，零数据丢失风险（j-t 数据 86 页里 1 页有，2 页 0 才停 → 错过 page 1 无 new 时的 page 2 概率 ~ 0）
- **B 激进（empty_pages ≥ 1）**：4s 完成，但有 ~0.1% 漏抓风险

**推荐 A**——漏数据成本 > 4s 节省，wrapper timeout 180s 给了 22x 余量。

**参考实现**：`scrape_sea_of_tranquility.py` 的 5 条连续 < cutoff 模式（`bin/scrape_sea_of_tranquility.py`，L267 附近）。但 j-t 的判定应该用"页"为粒度（`new_count==0` 即可），不是"条"，因为 j-t 的 in-window item 集中在 page 1。

## 4. 通用陷阱（不限于 j-t）

### 4.1 "卡住" 的四种实质

| 现象 | 实质 | 怎么验 |
|---|---|---|
| 真死循环 | `while` 条件永不 False | 看 log 翻页数，>100 = 死循环 |
| 结构性慢 | 翻页 / fetch / parse 累加超 timeout | 单步计时 |
| 网络慢 | 某个 fetch 60s+ | fetch DONE 时间戳 > 30s |
| 数据空 | parse 失败静默 | `grep "new reviews"` 永远 0 |

### 4.2 不要根据 SKILL.md 注释猜"会过滤"

**教训**：SKILL.md 写的"j-t 翻页多但 --days 1.5 会正确过滤"——**这注释误导了我**，让我以为早停内置。**修 SKILL.md 比修脚本优先**——下次别的 LLM 不会重蹈。

### 4.3 早停 = 3 种粒度

| 粒度 | 适合 | 例子 |
|---|---|---|
| **页** | 翻页循环，in-window 集中前 N 页 | j-t（推荐加） |
| **条** | 单页内 items 排序 | SoT 5 条连续 < cutoff |
| **时间** | 有 last-modified 头的 feed | RSS 1.5 天 cutoff |

**判定**：先看 `extract_reviews_from_html()` 返回的 items 是不是已经按日期排序——是就用"条"早停；不是就用"页"早停。

## 5. 关联 pitfalls

- SKILL.md §4 #10 "Scrape 卡住不一定是 hang"（本轮新增）
- SKILL.md §4 #2 "Cron session 写不出多行 Python"（本案例没踩，但同 session 相关）
- `references/scrape-script-cli-args.md` jazz_trail 行（本轮已更新"🔴 主循环无早停"警告）
- `references/2026-06-09-cron-heredoc-indent-failure.md` 顺带发现第 2 条（j-t 早停缺失）——本 reference 升级为独立文件
