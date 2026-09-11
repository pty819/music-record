# 调试 0 条站点 — 系统化方法

当 scrape 脚本返回 0 条时，需要区分：脚本 bug vs 站点无新内容 vs 站点封锁。

## 诊断步骤

### Step 1: 看 stderr 输出

```bash
python3 bin/scrape_X.py --days 7 2>&1 >/dev/null | head -30
```

关键信息：
- **"Found N items on listing page" + "SKIP (out of window)"** → 脚本正常，站点无新内容
- **"Found 0 items on listing page"** → 列表页解析失败或被封锁
- **"JSON parse error"** → stdout 有非 JSON 内容
- **无 stderr 输出** → 脚本崩溃

### Step 2: curl 检查实际页面

```bash
curl -sL 'https://site.com/reviews' -H 'User-Agent: Mozilla/5.0' | head -c 500
```

- **"Just a moment..."** → Cloudflare 拦截
- **HTML 有内容但脚本找不到** → 选择器/API 问题
- **空页面或 404** → 站点问题

### Step 3: 检查 SPA 特征

```bash
curl -sL 'https://site.com/reviews' | grep -c '__NEXT_DATA__\|__APOLLO_STATE__'
```

如果有结果，说明是 SPA，HTML 解析无效。需要：
1. 查找 GraphQL 端点：`curl site.com/graphql -d '{"query":"{ __typename }"}'`
2. 查找 REST API：检查 `__NEXT_DATA__` JSON 里的 `pageProps`
3. 或改用 Camoufox

### Step 4: 检查日期过滤

如果 Step 1 显示找到了文章但全被 SKIP，用更宽窗口测试：

```bash
python3 bin/scrape_X.py --days 30 2>&1 | grep "SKIP\|items"
```

如果 30 天窗口有数据，说明站点更新频率低，1.5 天窗口太紧。

## 已知案例

| 站点 | 问题 | 解决 |
|---|---|---|
| resident_advisor | Next.js SPA，HTML 无 review 元素 | 改用 `ra.co/graphql` |
| sea_of_tranquility | `<b>Added:</b>` 标签干扰日期正则 | `parse_added_date(strip_html(text))` |
| squids_ear | Cloudflare managed challenge | 2026-08-15 恢复（amer1 IP 下可访问，Amsterdam 仍 403） |
| bandwagon_asia | 正常，刚好错过 1.5 天窗口 | 无需处理 |
| downbeat | 月刊，2 个月没更新 | 无需处理 |

## Camoufox 也过不了的 Cloudflare

`squidco.com` 使用 Cloudflare **managed challenge**（非普通 JS challenge）：
- curl: "Just a moment..."
- Camoufox REST API: 等 10s 仍 "Just a moment..."
- 普通 JS challenge Camoufox 能过，managed challenge 不行

区分方法：看 challenge 页面是否有 `cType: 'managed'` 字段。
