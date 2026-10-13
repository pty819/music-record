# HTML 站 GraphQL/API 调查方法论

## 调查流程

当某个 HTML 站连续产出 0 条，需要判断是"真没内容"还是"脚本解析方式错误"。

### Step 1: 确认是 0 条还是脚本 bug

```bash
# 手动跑一次，看 stderr
python3 bin/scrape_<site>.py --days 1.5 2>&1 | head -20
```

### Step 2: 用浏览器/Camoufox 检查站点实际内容

```bash
# 看首页是否有内容
curl -sL -m 10 "https://example.com" | grep -c '__NEXT_DATA__\|__NUXT__\|gatsby\|graphql'
```

- `__NEXT_DATA__` = Next.js SPA → 查找 `props.pageProps` 里的 JSON 数据
- `__NUXT__` = Nuxt.js → 类似
- `gatsby` = Gatsby → 查找 `page-data.json`
- 无框架标记 = 传统服务端渲染 → HTML 解析应该有效

### Step 3: 检查隐藏 API 端点

```bash
# WordPress REST API
curl -sL -m 8 "https://example.com/wp-json/wp/v2/posts?per_page=1"
# RSS feed
curl -sL -m 8 -o /dev/null -w "%{http_code}" "https://example.com/feed/"
```

### Step 4: GraphQL 端点探测

对 Next.js SPA 站，检查 `/_next/data/` 或 `/graphql` 端点。RA 的案例：
- ra.co 是 Next.js SPA，HTML 里无 review 内容
- 但 `/graphql` 端点接受 POST 查询
- 查询 `reviews(1:5)` 返回完整 review 数据

## 已知结果（2026-06-10 调查）

| 站 | 框架 | 有 API？ | 处理 |
|---|---|---|---|
| resident_advisor | Next.js | GraphQL /graphql | ✅ 已改用 GraphQL |
| world_music_central | WordPress | RSS feed 活跃 | ✅ 已迁移到 RSS |
| free_jazzblog | WordPress | RSS 但 2016 停更 | 不值得迁移 |
| dark_entries_be | 静态 | ❌ | HTML 解析 OK |
| hear65 | 静态 | ❌ | HTML 解析 OK |
| squids_ear | Cloudflare | ⚠️ 2026-08-15 恢复（amer1 IP 可直连，其他节点仍 403）| Camoufox 不需要 |
| 其余 10 个 | WordPress/静态 | ❌ 404 | HTML 解析是唯一方式 |

## RA GraphQL 查询模板

```python
query = """
query {
  reviews(
    filters: {gte: {publishDate: "%s"}},
    sort: "publishDate:desc",
    pagination: {limit: 5}
  ) {
    data {
      id
      attributes {
        title
        publishDate
        body
        artists { name }
        genres { name }
        rating
      }
    }
  }
}
"""
```
