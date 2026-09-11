# 2026-08-15 Fluid Radio archive_pick 改造

## 背景

Fluid Radio（fluid-radio.co.uk）是英国 ambient / drone / electroacoustic
核心媒体，自 2022 年起乐评更新停滞。

历史上 `data/sites.json` 标 `crawl_strategy: skip`，notes 写"已一次性抓取
671 条存档，每次选专辑时从 fluid_radio_reviews.json 随机挑几条即可"——但
**这个存档文件从来没真正生成过**（git 历史不存在，本地磁盘也不存在）。

而不知何时配置被改成了 `has_rss: true` + `rss_url: https://www.fluid-radio.co.uk/feed/`，
重新纳入了每日 RSS 流程。结果发现：

- 根 `/feed/` 自 2026-08 被 SEO 博彩垃圾站劫持，**每天稳定产出 10 条
  "Non GamStop Casino" 系列**（验证 8-09、8-13、8-15 连续 3 天全污染）
- LLM 评分被迫给每条 1 分，污染每日推荐 + 浪费 10 次 MiniMax API 调用

## 正确 URL

主站仍然存活，正常乐评在分类页 `https://www.fluid-radio.co.uk/category/reviews/`
（不是根 feed）。该分类的 RSS 在 `https://www.fluid-radio.co.uk/category/reviews/feed/`，
**无博彩污染**，全部是 2013-2022 的高质量 ambient 乐评。

分页参数 `?paged=N` 可拉全量（实测 79 页，~790 条；去重后 800 条）。

## 解决方案：archive_pick 模式

不直接抓 RSS feed，而是**一次性拉全量存档 + 每日随机抽 N 条**。
优点：
- 0 重复内容（按 `_last_picked_date` 标记，重复推送同一旧内容会破坏日报新鲜感）
- 0 API 浪费（不会再有博彩污染触发 LLM）
- 0 抓取失败（存档是本地 JSON）

## 改动文件

1. `data/fluid_radio_archive.json`（新增，800 条 2013-2022 历史乐评）
2. `data/sites.json`（fluid_radio 站点配置）
   - `rss_url` → `https://www.fluid-radio.co.uk/category/reviews/feed/`
   - `reviews_url` → `https://www.fluid-radio.co.uk/category/reviews/`
   - 新增 `archive_source` 配置块
   - `notes` 重写说明新模式
3. `bin/fetch_fluid_radio_archive.py`（新增，一次性抓全量存档）
4. `bin/pick_fluid_radio_archive.py`（新增，每日随机抽 3 条）
5. `bin/fast-rss-scrape.py`
   - 加 `subprocess` import
   - 加 `_pick_from_archive(num=3)` 函数
   - `scrape_site()` 加 hook：site_id=fluid_radio 时改走 archive pick
6. `bin/process_reviews.py`
   - 加 `is_non_review_content()` 函数（含 fluid_radio_spam 规则作为兜底）
   - 加 `filter_breakdown` 到 `meta`

## 工作流程

```
cron 04:00 Step 2 (RSS 批量抓取)
  ├─ fast-rss-scrape.py 扫所有 has_rss=True 的站
  ├─ 普通站：feedparser 抓 feed
  └─ fluid_radio：子进程调用 pick_fluid_radio_archive.py
        ├─ 读 data/fluid_radio_archive.json (800 条)
        ├─ 过滤掉 _last_picked_date == 今天的
        ├─ 随机抽 3 条
        ├─ 标记 _last_picked_date = 今天
        ├─ 写回 archive
        └─ 返回 JSON（meta + items）

  后续流程与之前一致：merge_scraped → process_reviews → generate_report
```

## 验证数据（2026-08-15）

- archive 抓取：`fetch_fluid_radio_archive.py` → 800 条（79 页 × 10）
- 8-15 第一次 pick：Celer / Unknown Tone… / Thesis 01
- 8-15 第二次 pick（验证去重）：3 条完全不同
- archive 中 `_last_picked_date` 正确更新

## 重新生成存档

```bash
python3 bin/fetch_fluid_radio_archive.py           # 全量 80 页
python3 bin/fetch_fluid_radio_archive.py --max-pages 5   # 测试前 5 页
```

预计耗时：全量约 30-60s（10 线程并发）。

## 故障排查

| 症状 | 原因 | 处理 |
|---|---|---|
| archive 不存在 | 首次运行前 archive 文件未生成 | 跑 `fetch_fluid_radio_archive.py` |
| pick 后 _last_picked_date 没更新 | 子进程未正常退出 | 检查 pick_fluid_radio_archive.py 直接调用是否 OK |
| fluid_radio 当天仍 0 条 | archive 被某次 pick 全部标今日（极端情况下，pool 耗尽自动 reset 30%） | 检查 archive meta，必要时手动 reset |
| rss_merged.json 中 fluid_radio 出现博彩词 | hook 未生效，sitemgr 走错路径 | 检查 fast-rss-scrape.py 的 site_id 分支 |
