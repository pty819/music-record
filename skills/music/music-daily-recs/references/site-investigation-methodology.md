# Site Investigation Methodology

When a site returns empty scraper results, systematically investigate (in order):

## Phase 1: Quick triage

### 1. Check JSON output
```bash
cat ~/music-record/2026/05/2026-05-14/{site_id}_reviews.json
```
- Empty `[]` → scraper ran but found nothing
- Non-empty but `"excerpt": ""` → scraper found entries but couldn't get text

### 1b. 先分清「脚本坏了」和「站没发文」——两者外部表现完全一样

一个站返回 0 条，有两种完全不同的原因，而**两者在日志里长得一模一样**（都是 `0 items`，都没有报错）：

- **脚本坏了**：选择器过时、URL 改了、站点改版 → 改选择器能救
- **站没发文**：选择器完全正常，只是最近没发新东西 → **改选择器一点用没有，还会把本来能用的脚本改坏**

判定方法只有一个：**逐步放宽时间窗，看条数在哪一档跳出来。**

```bash
for d in 1 30 120 400; do
  printf "  --days %3d -> " "$d"
  python3 bin/scrape_<name>.py --days "$d" 2>/dev/null | \
    .venv/bin/python -c "import json,sys; print(len(json.load(sys.stdin).get('items',[])),'条')"
done
```

读法：

- `1/30/120` 全是 0，`400` 突然有十几条 → **站点停更，选择器是好的**。此时去「修选择器」是在做负功。
- 所有档位都是 0 → 才是选择器/URL 的问题。

⚠️ 看到列表页能解析出文章链接就下结论「选择器过时」是错的——要**再确认这些文章的发布日期**。实测：`downbeat` 的 12 篇文章全部正常解析、旧选择器（`col-sm-7 col-sm-push-2`、`category-list`）全都还在，但发布日期是半年前，所以 1.5 天窗口内自然是 0 条。**链接能拿到 ≠ 在时间窗内。**

先跑这一条，再决定要不要动代码。

### 2. Check sites.json config
Look up the site in `/home/liyifan/.minimax/music-sites/sites.json`:
- `reviews_url` — where the scraper looks
- `has_rss` — RSS URL if configured
- `crawl_strategy` — playwright_headless / http_get / skip

### 3. Test RSS first (fastest)
```bash
curl -sL --max-time 10 "https://site.com/feed/" | head -5
# Expect: <?xml / <rss / <feed → valid
# Expect: DOCTYPE / 403 / 404 → invalid
```

If RSS valid, check dates:
```bash
python3 -c "
import feedparser
feed = feedparser.parse('https://site.com/feed/')
for e in feed.entries[:5]:
    pub = e.get('published','?')
    title = e.get('title','')[:60]
    print(f'{pub} | {title}')
"
```

### 4. Test HTTP status of reviews_url
```bash
curl -sL -o /dev/null -w "%{http_code}" --max-time 8 "https://site.com/reviews"
```

| Status | Meaning |
|--------|---------|
| 200 | Site accessible |
| 403 | Cloudflare / bot block |
| 404 | Wrong URL |
| 500 | Server error (broken path) |
| timeout | Site slow or down |

## Phase 1.5: RSS / 服务端渲染探测（免浏览器的前提）

**不要因为一个站「现在走浏览器」就断定它必须走浏览器。** 绝大多数被判死刑的站只是没人找过 feed。本机 1.6GB 根本跑不动浏览器，所以每个新站接进来之前先跑这套探测——纯 HTTP，不消耗内存。

### A. 找真 RSS

按可靠性依次试：

1. **页面自己声明的**（最准，很多站有 feed 但不在常见路径上）：抓首页再 grep `<link>` 标签里 `type` 为 `application/rss+xml` 或 `application/atom+xml` 的，取出其中的 `href`。`musique_machine` 的 `/feed.xml` 就是这么找到的——它不在 `/feed` 也不在 `/rss`。
2. **常见路径批量试**：`/feed` `/feed/` `/rss` `/rss.xml` `/feed.xml` `/atom.xml` `/index.xml` `/blog/feed` `/news/feed` `/reviews/feed` `/articles/feed`
3. **判定**：`<?xml` / `<rss` / `<feed` 开头，或前 3000 字节里有 `<item` / `<entry` → 算命中。

### B. 判定服务端渲染（SSR）

列表页 200 不等于有用，要看**文章详情页**：存盘后先看字节数（小于 20KB 通常是 JS 壳），再数长 `<p>` 段落。

- **正文≥3 段、字数 >1500** → 服务端渲染，纯 HTTP 可用
- **段落少、字数小、正文在 `<script>` 里** → 真 JS 渲染，必须浏览器（本机不要接）

⚠️ 过滤正文时要去掉导航/订阅/版权类短段落，并**排除 `class` 形如 `body|article|content|review` 的容器**。匹配到 nav 会得到一个看似很大的数字而实际全是菜单。

⚠️ 列表页链接必须用 `urljoin` 拼绝对 URL。有些站写协议相对 URL（`//www.example.com/...`），直接字符串拼接会得到双 host 的畸形 URL 然后全线 404——**看起来像站点全挂，其实是自己的探测脚本有 bug**。

### C. URL 路径会漂移

站点的 section 路径改名后，旧 URL 静默 404（不是 500、不是空列表）。探测时**以首页实际链接为准**，不要信 `sites.json` 里的 `reviews_url`：`mixmag` 的 `/asia/` 已 404，实际列表在 `/features/`。

### D. RSS 摘要够不够评分

RSS 未必带全文。检查 `content:encoded` 出现次数：为 0 就说明只有 `description`，且常被截断（实测 300 字符）。

300 字摘要能支撑评分，但拿不到全文细节。**发现截断就要知道质量上限**，不要以为抓到了完整乐评。

### E. 页面上的日期不一定属于文章——先确认它挂在哪个元素上

判「站点还在更新」时，页面上出现过一个近期日期不等于有新文章。日期可能来自：

- **月份归档下拉框的 `<option>`**（`<option value="/reviews/editorspicks/september-2026">September 29, 2026</option>`）
- 侧栏的「最新文章」widget、面包屑、JS 变量、meta 标签

实测踩过：`downbeat` 页面里明明有 "September 29, 2026"，据此差点判成「站点仍在更新、只是选择器过时」，结论完全反了。真实情况是文章列表最新只到半年前，而那个日期只是下拉框里列出的**归档月份**。

**判定方法：把日期字符串反查到它的宿主元素，再确认宿主是不是文章块。**

```bash
# 找出是哪个元素带着这个日期
python3 -c "
import re,urllib.request
from bs4 import BeautifulSoup
h=urllib.request.urlopen(urllib.request.Request('URL',headers={'User-Agent':'Mozilla/5.0'}),timeout=20).read().decode('utf-8','replace')
s=BeautifulSoup(h,'lxml')
for t in s.find_all(string=re.compile(r'September 29, 2026')):
    p=t.parent
    print(f'<{p.name} class={p.get(\"class\")}>')"
```

只信**列表页每篇文章块内部**的日期（本文路径下是 `<p class="postinfo">`）。

### F. 猜归档参数全部返回同一页 = 参数根本没生效

排查归档路径时，`?month=4&year=2026`、`?m=4&y=2026`、`?date=2026-04` 如果返回**字节数几乎相同、日期范围完全一致**的结果，说明这些参数被服务端忽略了——不是「参数组合错」，是站点根本不认这套查询串。

```bash
for q in "?month=4&year=2026" "?m=4&y=2026" "?date=2026-04"; do
  printf "%-22s " "$q"
  curl -sL --max-time 15 "https://site.com/reviews$q" | \
    grep -oE '<p class="postinfo">[^<]+' | head -1
done
```

真实归档路径通常**直接写在 `<option value>` 里**，从下拉框读比猜查询参数快得多：

```bash
grep -oE '<option[^>]*value="[^"]*"' | grep -i review
# → /reviews/editorspicks/september-2026
```

### G. 「有归档页」不等于「有文章」

归档页 HTTP 200 不代表里面有内容。逐月检查 `<article>` 与 detail 链接的**数量**，而不是只看状态码：

```bash
for mo in april-2026 may-2026 june-2026 july-2026; do
  printf "%-16s " "$mo"
  curl -sL --max-time 15 "https://site.com/reviews/editorspicks/$mo" | \
    grep -coE '<article|reviews/detail/[a-z0-9-]+'
done
```

全 0 且页面只剩 JS 骨架，进一步印证栏目停更。**只报状态码会把一个空归档页读成「有归档可用」。**

### 已知结论（仅供对照，站点状态会变，以实际探测为准）

| 站 | RSS | SSR | 判定 |
|---|---|---|---|
| musique_machine | 有，`/feed.xml`（约 30 条，description 截断 300 字，`content:encoded` = 0） | — | **可走 RSS** |
| downbeat | 无 | 有，文章模式 `/reviews/detail/<slug>`，实测正文 1700+ 字，**选择器无问题** | **纯 HTTP 可用，但 `/reviews` 自 2026-04-18 停更**（`--days 400` 才 12 条）。要新内容得另抓 `/magazine`（该栏目有当月内容，结构不同） |
| mixmag | 无（`/feed/`、`/asia/feed/` 均 404） | 部分，正文选择器不干净、混入 CSS；`/asia/` 已 404，实际列表在 `/features/` | 收益低，暂不接 |
| all_about_jazz | 无 | 否，详情页取到的是导航文字 | 真 JS 渲染，本机放弃 |

## Phase 2: Browse investigation (for Playwright sites)

Use `browser_navigate` to visit the `reviews_url` and check:

1. **Wrong URL?** Navigate the site's navigation to find the correct reviews section
2. **Paywalled?** Check if individual review pages need login/subscription
3. **No dates?** Check if list page shows publication dates (needed for 3-day filter)
4. **Click-through needed?** Some sites list only titles on the list page; actual content is on individual pages

## Phase 3: Find correct URL (when current URL is wrong)

Try common paths:
```
/reviews
/category/reviews
/reviews-hub
/music
/album-reviews
/editorial
/features
```

Check site navigation via browser_snapshot — look for links named "Reviews", "Album Reviews", "Music", "Articles".

## Phase 4: Classify the finding

| Cause | Action |
|-------|--------|
| Wrong URL | Update `reviews_url` in sites.json |
| Broken RSS URL | Fix `rss_url` or switch to `has_rss: false` + playwright |
| No recent content (3+ day window) | Accept as-is, or publish wider window for low-frequency sites |
| Cloudflare 403 | Add to Cloudflare list; accept metadata-only |
| Site dead/moved | Mark `crawl_strategy: skip` |
| Agent execution bug | Debug scraper body template or agent environment |
| Feature format (not album review) | Add `type: feature` handling to scraper body |

## 2026-05-14 Full Audit Results

See `references/scraper-diagnostics-2026-05-14.md` for the complete 42-site investigation results.
