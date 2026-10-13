# 站点层级迁移方法论

## 什么时候迁移

当一个 HTML 站的脚本长期返回 0 条，但手动检查发现站有内容时，检查是否应该迁移到更高效层：

- **HTML → RSS**：站点有可用 RSS feed（`curl -sL <url>/feed/` 返回 200 + `<item>` 或 `<entry>`）
- **HTML → Camoufox**：站点是纯 SPA（Next.js/Nuxt），curl 拿不到内容，也没有 API

## 迁移步骤（以 HTML → RSS 为例）

### 1. 确认 RSS feed 可用

```bash
# 检查 feed 是否存在且有内容
curl -sL -m 10 "https://example.com/feed/" | grep -c '<item>'
# 检查是否有近期内容
curl -sL -m 10 "https://example.com/feed/" | grep -oP '<pubDate>[^<]+</pubDate>' | head -3
```

### 2. 修改 sites.json（唯一源）

```python
# data/sites.json
{
  "id": "站点名",
  "has_rss": True,           # 原来是 False
  "rss_url": "https://...",  # 确保有值
  "crawl_strategy": "http_get"  # 原来是 playwright_headless
}
```

**注意**：只改 `data/sites.json`，不要改其他位置的副本。

### 3. 从 HTML_SCRIPT_IDS 移除

```python
# bin/kanban-swarm.py
HTML_SCRIPT_IDS = frozenset({
    # 删除 "站点名" 这一行
})
```

### 4. 更新 SKILL.md

- RSS 列表加站点名
- HTML 表删除该行
- 计数更新（如 28→29 RSS, 17→16 HTML）

### 5. 验证

```bash
# 测试 RSS 抓取
python3 bin/fast-rss-scrape.py --days 1.5 --workers 4 -o /tmp/migration-test.json
# 确认新站出现在输出中
python3 -c "import json; d=json.load(open('/tmp/migration-test.json')); print([i for i in d['items'] if '站点名' in str(i)])"
```

### 6. 提交

```bash
git add -A && git commit -m "feat: migrate 站点名 from HTML to RSS" && git push
```

## 调查 HTML 站 0 条的方法

1. **curl 检查**：`curl -sL -m 10 <url>` 看 HTTP 状态码和内容
2. **检查框架**：`grep -c '__NEXT_DATA__\|__NUXT__\|gatsby'` 判断是否 SPA
3. **检查 API**：
   - WordPress: `<url>/wp-json/wp/v2/posts?per_page=1`
   - GraphQL: 查看页面源码是否有 `graphql` 端点
   - RSS: `<url>/feed/`
4. **Camoufox 验证**：如果 curl 被拦截，用 Camoufox REST API 访问
5. **对比脚本逻辑**：看脚本的解析选择器是否匹配实际 HTML 结构

## 已知案例

| 站 | 原层 | 新层 | 原因 |
|---|---|---|---|
| world_music_central | HTML | RSS | 有活跃 RSS feed，curl 直接可用 |
| resident_advisor | HTML | HTML（修 bug） | Next.js SPA，改用 GraphQL API |
| sea_of_tranquility | HTML | HTML（修 bug） | `<b>` 标签干扰日期正则 + Nov=10 拼写错误 |
