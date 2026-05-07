# Music Daily Recs — 快速参考

> 本文件是执行摘要，完整文档见 SKILL.md。

## 架构概览

```
cron/手动触发
    ↓
Step 1: kanban-batch-scrape.py → 43 个 scraper 任务（parallel）
    ↓ (全 done)
Step 2: aggregator → 合并去重 → aggregated.json
    ↓
Step 3: filter → 评分排序 → filtered.json + markdown
    ↓
Step 4: writer → git push → GitHub
    ↓
Step 5: notifier → Telegram top 20
```

## 站点分布（43 活跃 + 3 skip）

| 类别 | 数量 | 代表站 |
|---|---|---|
| RSS + Playwright | ~21 | The Quietus, A Closer Listen, Bandcamp Daily, Igloo Magazine |
| Playwright only | ~22 | DownBeat, All About Jazz, Free Jazz Blog, Songlines |
| skip | 3 | Boomkat（IP段被禁）, Syrphe（不稳定）, Textura（JS空白） |

## ⚠️ Fluid Radio — 静态存档

RSS 灌入 2013–2022 全部历史存档（671 条），无新内容。`crawl_strategy=skip`。

Aggregator 额外从历史存档**随机抽取 2–3 条**，标注 `[Fluid Radio Archive]`。

## ⚠️ The Wire — 已确认 paywalled

/ category/reviews 返回 404。RSS 返回 HTML。跨站搜索无有效评论。

**结论：标记 `status=paywalled`，不重试。**

## ⚠️ scraper auth.json — 只留 minimax-cn

检查：

```bash
cat ~/.hermes/profiles/scraper/auth.json
```

确保只有 `minimax-cn`（api.minimaxi.com）。若有 `minimax`（api.minimax.io）共存 → **401 崩溃 5 次后放弃**。

## 评分阈值

- **主推荐**：总分 >= 9
- **候选补充**：总分 6-8
- **全部写入**：>= 6 分全部保留，无上限

## 今日批次开始前必做

```bash
# 1. 检查积压
hermes kanban list | grep "◻" | grep "scrape:" | wc -l

# 2. 清理旧 todo scraper
hermes kanban list | grep "◻" | grep "scrape:" | awk '{print $2}' | while read id; do
  hermes kanban archive "$id"
done

# 3. 确认 scraper profile 可用
cat ~/.hermes/profiles/scraper/auth.json
cat ~/.hermes/profiles/scraper/config.yaml
```

## 两套输出

- **GitHub**：全量 markdown + JSON，路径 `2026/{MM}/{YYYY-MM-DD}.md`
- **Telegram**：top 20 主推荐，精简格式

## 关键文件路径

| 文件 | 路径 |
|---|---|
| sites.json | `/home/liyifan/.minimax/music-sites/sites.json` |
| scraper 输出 | `/home/liyifan/.minimax/music-sites/output/` |
| daily_recs.md | `/home/liyifan/.minimax/music-sites/output/daily_recs.md` |
| aggregated.json | `/home/liyifan/.minimax/music-sites/output/aggregated.json` |
| filtered.json | `/home/liyifan/.minimax/music-sites/output/filtered.json` |
