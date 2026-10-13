# RSS URL Injection into Scraper Body Template

## 背景

`kanban-swarm.py` 的 `build_scraper_body()` 模板包含 `url`（站点首页），但**不**包含 `rss_url`（来自 `sites.json`）。

模板 Step 1 说：
```
1. 检查 RSS → curl + feedparser，过滤 36 小时内条目
```

但没有 RSS URL，worker 只能自己猜测路径——不可靠。`crawl_strategy: playwright_headless` 标记的站尤其容易跳过 RSS 发现直接走浏览器。

## 受影响站点（已有 RSS 但仍标 Camoufox）

| Site | RSS URL |
|------|---------|
| VAN Magazine | `https://van-magazine.com/feed/` |
| Jazz Journal | `https://jazzjournal.co.uk/feed/` |
| The Classic Review | `https://theclassicreview.com/feed/` |
| Igloo Magazine | `https://igloomag.com/feed` |
| Bandcamp Daily | `https://daily.bandcamp.com/feed` |
| Prog Mistress | `https://progmistress.com/feed` |
| The Rest Is Noise PH | `https://therestisnoiseph.com/feed` |

## 修复

在 `kanban-swarm.py` 的 `build_scraper_body()` 注入 `rss_url`：

```python
rss_url = site.get("rss_url", "")
# 在 body 头注入 rss 字段
```

worker body 顶部应包含 rss URL（如果有），让 worker 知道"用现成的 RSS URL，不要自己探索"。

## 完整升级流程

详见 `camoufox-to-rss-promotion.md`：

1. `feedparser.parse(url)` 验证 status=200/301 且 entries > 0
2. 修改 `sites.json`：`has_rss: true, crawl_strategy: "http_get"`
3. 同步到 `~/.minimax/music-sites/sites.json`
4. `kanban-swarm.py` 自动过滤此站，不再创建 Camoufox worker
