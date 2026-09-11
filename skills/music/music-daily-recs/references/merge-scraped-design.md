# merge_scraped.py — 设计文档

## 职责

将三路抓取输出合并为一个统一 JSON 文件 `scraped_raw.json`：

| 源 | 文件 | 产出脚本 |
|----|------|---------|
| RSS 批量 | `rss_merged.json` | `fast-rss-scrape.py` |
| HTML/curl 各站 | `*_reviews.json` | `scrape_*.py`（12 个） |
| Camoufox kanban worker | `*_reviews.json` | kanban worker 按模板产出 |

## 合并规则

### 1. 输入格式兼容

自动处理两种输入格式：
- `dict` → `{"meta": {...}, "items": [...]}` — RSS scraper + HTML/curl scraper 标准格式
- `list` → `[...]` — 旧版 kanban worker 格式（现已不再产生此格式，保留兼容）

### 2. URL 去重（默认开启）

按 `item["url"]` 去重，保留首次出现（即优先 RSS 版本，因为 rss_merged.json 在 glob 中排第一）。

去重顺序：`rss_merged.json` 显式排第一 → `sorted(glob("*_reviews.json"))` → RSS 版本优先。

### 3. 排序

按 `pub_date` 降序（最新在前）。

### 4. 幂等性

完全幂等：重跑会重新读取目录下所有文件，去重重写。可安全反复执行。

### 5. 跳过逻辑

自动跳过 `scraped_raw.json`、空文件（size < 5B）、JSON 解析失败的文件。

### 6. site_id 兜底

缺少 site_id 的条目从文件名推断：`downbeat_reviews.json` → `site_id="downbeat"`。

## 输出格式

```json
{
  "meta": {
    "total": 108,
    "merged_from": {
      "free_jazz_blog_reviews.json": 2,
      "rss_merged.json": 106
    },
    "scraped_at": "2026-05-26T03:53:29+00:00"
  },
  "items": [
    { "album": "...", "artist": "...", "score": null, "url": "...",
      "source": "...", "pub_date": "...", "tags": "...",
      "excerpt": "...", "body": "...", "site_id": "...",
      "crawl_status": "success", "type": "review" }
  ]
}
```

`merged_from` 记录各源文件名及条目数，用于审计。

## 用法

```bash
# 合并当日数据，输出 scraped_raw.json
python3 merge_scraped.py --date-dir "2026/05/2026-05-26" -o scraped_raw.json

# 跳过去重
python3 merge_scraped.py --date-dir "..." --no-dedup

# 绝对路径
python3 merge_scraped.py --date-dir "/home/liyifan/music-record/2026/05/2026-05-26"
```

## 注意事项

- 不承担格式兼容职能（约束 #6），兼容旧格式仅作为被动安全网
- 108 条去重排序 < 0.1s，性能不是瓶颈
- 源：`music-record/bin/merge_scraped.py` → 执行：`~/.local/bin/`
