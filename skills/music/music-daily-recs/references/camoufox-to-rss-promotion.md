# Camoufox → RSS 提升指南

**背景：** 2026-05-25 发现 28 个标记为 `playwright_headless` 的站中有 7 个实际有可用 RSS feed。
这些站走 Camoufox 浏览器很慢/常挂，切到 RSS（`has_rss: true, crawl_strategy: http_get`）后 `fast-rss-scrape.py` 几秒搞定。

## 定期巡检清单

每隔一段时间（月/季度），检查一下 Camoufox 站是否有新的 RSS 出现：

```bash
python3 -c "
import feedparser
# 填 Camoufox 站的候选 RSS 地址测试
urls = {
    'van_magazine': 'https://van-magazine.com/feed/',
    'jazz_journal': 'https://jazzjournal.co.uk/feed/',
    # 加更多...
}
for name, url in urls.items():
    f = feedparser.parse(url)
    n = len(f.entries)
    s = f.get('status', '?')
    print(f'{name:>25}  status={s:>3}  entries={n}')
"
```

## 验证标准

| 条件 | 判定 |
|------|------|
| status=200 且 entries>0 | ✅ 可用，可以升 |
| status=301→200 且 entries>0 | ✅ 301 重定向正常，可以升 |
| status=403/404/bozo | ❌ 不可用，保持 Camoufox |

## 升级操作

```python
# sites.json 中对应站点修改：
{
    "rss_url": "https://...",
    "has_rss": true,
    "crawl_strategy": "http_get"
}
```

同步到 repo：`cp sites.json music-record/data/sites.json` 然后 `git push`。

## 已知验过的站

2026-05-25 已验证升为 RSS 的 7 个站见 SKILL.md 各站特殊处理表。
其余 Camoufox 站已验证无 RSS：
- Boomkat: 403
- Squid's Ear: 403  
- All About Jazz: 302→非RSS
- DownBeat/Songlines/RA/Free Jazz Blog/Musique Machine: 404
- ProgArchives: 403（全站CF）