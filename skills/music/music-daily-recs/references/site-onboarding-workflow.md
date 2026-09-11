# Site Onboarding Workflow

Process for adding a new music review site to the pipeline — from candidate selection to commit.

## Phase 0: Candidate → Research

### 0.1 Collect candidate metadata
- Site name, homepage URL
- What genre(s) it covers
- Check if the site is still alive
- Evaluate content quality (recent reviews, not just news)

### 0.1b Multi-language site discovery
When searching for niche genres (e.g. Japanese noise, Korean experimental), **use native-language keywords in web_search** — don't assume English-only results. Example: `日本 ノイズ音楽 レビュー ブログ` finds sites that English queries miss. The search engine handles non-ASCII fine.

**Multi-channel search is mandatory** — don't rely on a single search MCP. User explicitly requires: Brave MCP + MiniMax MCP + browser direct access. Different tools surface different results, especially for niche/non-English content. For Japanese sites, also try `search_lang=jp` on Brave.

**Key resource for Japanese experimental music**: [free-impro.jp/media](https://free-impro.jp/media) is a curated directory of Japanese free improvisation/experimental music web media, and [free-impro.jp/blog](https://free-impro.jp/blog) lists personal blogs. These are goldmines for Japanese avant-garde site discovery.

### 0.2 Determine access method (RSS first, always)

Test RSS in priority order using curl:

```bash
# Common RSS paths
curl -sL --max-time 10 "https://site.com/feed/" | head -5
curl -sL --max-time 10 "https://site.com/rss" | head -5
curl -sL --max-time 10 "https://site.com/feed/rss/" | head -5
curl -sL --max-time 10 "https://site.com/index.xml" | head -5

# Check homepage for RSS link
curl -sL --max-time 10 "https://site.com" | grep -i "rss\|feed\|xml\|atom" | head -5
```

**Expected output**: `<?xml` / `<rss` / `<feed` → valid RSS.  
**Unexpected**: DOCTYPE / 403 / 404 / lander redirect → invalid path.

### 0.3 Validate RSS content

```bash
# Check item count, dates, titles
python3 -c "
import feedparser
feed = feedparser.parse('VALID_RSS_URL')
for e in feed.entries[:3]:
    pub = e.get('published','?')[:16]
    t = e.get('title','')[:60]
    print(f'[{pub}] {t}')
print(f'Total items: {len(feed.entries)}')
"
```

Criteria:
- Has recent items (within 3 days) → ✅ daily-capable
- Only has old items → low-frequency / skip
- Items have titles with artist: album format → easy to parse
- Has `pubDate` field → can apply 3-day window filter

### 0.4 Camoufox fallback (when RSS fails)

If RSS returns 403/404/empty/lander, test via browser:

```bash
browser_navigate(url="https://site.com/")
browser_snapshot()  # Check if site loads, look for reviews section
browser_navigate(url="https://site.com/recensies")  # Try common paths
```

If site loads but has no RSS → `crawl_strategy: playwright_headless` + `has_rss: false`
If site returns Cloudflare JS challenge or SSL error → mark as inaccessible

### 0.4b Network-level accessibility testing (when all methods fail)

When curl、Python requests、Camoufox 都无法连接某站点，按以下路径排查：

```bash
# 1. curl 基础测试
curl -sL -o /dev/null -w "HTTP %{http_code} | Time: %{time_total}s" \
  --connect-timeout 8 --max-time 12 "https://site.com/"

# 2. Python requests 测试
python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
try:
    resp = urllib.request.urlopen('https://site.com/', timeout=10, context=ctx)
    print(f'HTTP {resp.status}')
except Exception as e:
    print(f'{type(e).__name__}: {e}')
"

# 3. DNS 解析（确认 IP 是否可达）
python3 -c "
import socket
results = socket.getaddrinfo('site.com', 443)
print(f'IP: {results[0][4][0]}')
"

# 4. OpenSSL TLS 握手测试
echo | openssl s_client -connect site.com:443 -servername site.com 2>&1 | head -20

# 5. Camoufox 测试（如果以上都失败）
python3 -c "
import requests
r = requests.post('http://localhost:9377/tabs', json={
    'userId': 'test', 'sessionKey': 'test', 'url': 'https://site.com/'
}, timeout=30)
print(r.json())  # 看是否有 NS_ERROR_NET_INTERRUPT
"
```

### 判断逻辑

| curl | Python | Camoufox | 结论 |
|------|--------|----------|------|
| ✅ 200 | ✅ | ✅ | 正常站点 |
| ❌ SSL | ❌ SSL | ❌ NS_ERROR_NET_INTERRUPT | **网络层问题**（TLS 握手失败，非浏览器兼容性） |
| ❌ 403 | ❌ 403 | ✅ | Cloudflare 反爬 → Camoufox |
| ❌ timeout | ❌ timeout | ❌ timeout | 站点宕机或 IP 被封 |
| ❌ SSL | ❌ SSL | ✅ | TLS 兼容性问题 → Camoufox 可绕过 |

**关键判断**：Camoufox (Firefox 引擎) 的 TLS 栈与 curl/Python 不同。如果 Camoufox 能通但 curl 不行，说明是 TLS 配置兼容性问题，Camoufox 可以绕过。如果 Camoufox 也报 `NS_ERROR_NET_INTERRUPT`，说明是**网络层问题**（IP 被封、TLS 握手被服务器主动断开），需要放弃该站点。

**已知案例**：部分日本站点（28.0.0.x 段 IP）从中国大陆服务器 HTTPS 连接时 TLS 握手被服务器主动断开（读到 0 字节），但 HTTP 能通。这种站点如果必须 HTTPS 则不可用。

### 0.5 Determine review URL

Find the page that lists reviews (not just news/promos):
```bash
# Common review paths to try
/reviews /recensies /reviews-hub /music /album-reviews /editorial /features /articles
```

Navigate to the review list page → confirm it has:
- ☐ Per-review titles (artist + album)
- ☐ Publication dates
- ☐ Excerpt or full text

### 0.6 Batch RSS validation
For adding multiple sites at once, use `execute_code` to check all RSS feeds in one pass — check HTTP status, XML parsing, encoding, item count, dates, and link presence. This catches encoding issues (e.g. Japanese sites using Shift-JIS) that simple curl checks miss.

### 0.7 HTML scrape script testing
When writing a new HTML scrape script (`scrape_<id>.py`):
- **Test with `--days 1`** (not `--days 7`) — larger windows mean more article pages to fetch, easily timing out.
- Use `ThreadPoolExecutor` for concurrent article page fetching (6-8 workers).
- Output must be `{"meta": {...}, "items": [...]}` to stdout (consumed by `scrape_html_parallel.py`).
- Each item needs: `album`, `artist`, `body`, `source`, `pub_date`, `url`, `site_id`, `tags`, `type`.
- **Must be added to BOTH** `kanban-swarm.py:HTML_SCRIPT_IDS` **AND** `scrape_html_parallel.py:SCRIPTS` — verify with `grep -c <id> bin/scrape_html_parallel.py` (=1).

### 0.7b note.com RSS pattern
Japanese niche music bloggers often use note.com. RSS format:
```
https://note.com/<username>/rss
```
Returns standard RSS XML. Items have `pubDate` and content in `<description>`. These are high-value for Japanese underground/experimental music coverage.

### 0.8 RSS site batch discovery
When discovering sites in bulk (e.g. from a curated directory page):
1. Extract all candidate URLs from the directory page
2. Batch-check RSS availability with `execute_code` (check common paths: `/feed/`, `/feed`, `/rss/`, `/atom.xml`, `/rss.xml`)
3. Deep-validate working feeds: XML parsing, encoding, item structure, date parsing
4. Categorize results: RSS (add directly) → HTML scrapable (write script) → Camoufox needed (add with crawl_strategy)

## Phase 1: Configure sites.json

### 1.1 Build the entry

Template for RSS sites:
```json
{
  "id": "site_id",
  "name": "Site Name",
  "homepage": "https://site.com/",
  "rss_url": "https://site.com/feed/",
  "reviews_url": "https://site.com/",
  "has_rss": true,
  "tier": "B",
  "crawl_frequency": "daily",
  "parser_hint": {
    "article_url_pattern": "site.com/",
    "list_selector": "article h2 a",
    "body_selector": "article .entry-content p"
  },
  "tags": ["industrial", "darkwave", "goth"],
  "notes": "简要说明",
  "startUrls": ["https://site.com/"],
  "automationStatus": "default_on",
  "crawl_strategy": "http_get"
}
```

Template for Camoufox/browser sites:
```json
{
  "id": "site_id",
  "name": "Site Name",
  "homepage": "https://site.com/",
  "rss_url": null,
  "reviews_url": "https://site.com/reviews",
  "has_rss": false,
  "tier": "B",
  "crawl_frequency": "daily",
  "parser_hint": {
    "article_url_pattern": "site.com/",
    "list_selector": "article h2 a",
    "body_selector": "article .el-content p",
    "notes": "需 Camoufox。首页列表可直接提取无需点详情页。"
  },
  "tags": ["gothic", "industrial", "darkwave"],
  "notes": "站点说明",
  "startUrls": ["https://site.com/"],
  "allowUrlPatterns": ["/reviews/"],
  "denyUrlPatterns": ["/about", "/contact"],
  "parserHints": {
    "articleSelectors": ["article", ".uk-article"],
    "titleSelectors": ["h1", "h3"],
    "dateSelectors": ["time", ".date"],
    "linkRowSelectors": ["article a", ".uk-card a"]
  },
  "automationStatus": "default_on",
  "crawl_strategy": "playwright_headless"
}
```

### 1.2 Tier assignment

| Tier | When | Notes |
|------|------|-------|
| **S** | Proven core site, high volume, tight fit | The Wire, AAJ, RA, The Quietus |
| **A** | Good quality, moderate volume | Songlines, Bandcamp Daily, JazzTimes |
| **B** (default for new) | Unproven / specialized / lower volume | All new sites start here until quality verified |

### 1.3 Tags — critical for scoring

Tags are used by the scoring formula (`score_review`) to determine taste_match baseline.

For darkwave/dark electronic sites, typical tags:
- `industrial`, `darkwave`, `EBM`, `electro`, `post-punk`, `goth`
- `synth`, `shoegaze`, `alternative`, `underground`
- `gothic rock`, `dark electro`

These tags feed into `site_base` scoring: industrial/darkwave/EBM → avant-garde matching.

### 1.4 Add to crawl_priority

Append the site ID to the appropriate tier group in `crawl_priority`.

## Phase 2: Update SKILL.md

Add the new site to the site table in SKILL.md:

```markdown
| `site_id` | Site Name | 访问方式 | 覆盖风格 |
```

Also add a ⚠️ note for any site-specific gotchas (e.g. ISO-8859-1 encoding, Dutch language, HTTP-only RSS).

## Phase 3: Commit & push

```bash
cd ~/music-record
cp /home/liyifan/.minimax/music-sites/sites.json data/sites.json
cp /home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md skills/music/music-daily-recs/
git add data/sites.json skills/music/music-daily-recs/SKILL.md
git commit -m "Feat: add {site_id} ({crawl_strategy}) to pipeline"
git push
```

## Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| **RSS encoding garbled** | CJK sites may use Shift-JIS or EUC-JP instead of UTF-8 | Test with `ET.fromstring(resp.content)` not just `resp.text`; use `resp.content` for XML parsing |
| **HTML scrape script timeout** | Tested with `--days 7` which fetches too many article pages | Always test with `--days 1` first |
| **Camoufox sites not picked up** | `get_sites()` in kanban-swarm.py filters by: not skip, not has_rss, not in HTML_SCRIPT_IDS | Sites with `crawl_strategy: "camoufox"` and `has_rss: false` auto-route to Camoufox |
| **Japanoise.com unreachable** | Academic book site, not a review site | Skip — it's a reference, not a scraping target |
| **WordPress sites with JS frameworks** | Vue/React rendered WordPress (e.g. musicircus) | Needs Camoufox, not simple HTTP scrape |

## Verification checklist (before commit)

- [ ] `curl -sL --max-time 10 "rss_url" | head -5` → valid XML (for RSS sites)
- [ ] `browser_navigate(url=reviews_url)` → loads successfully (for Camoufox sites)
- [ ] JSON valid: `python3 -m json.tool sites.json > /dev/null`
- [ ] site ID added to `crawl_priority` tier group
- [ ] `has_rss` matches actual RSS availability
- [ ] `crawl_strategy` matches access method (`http_get` for RSS, `playwright_headless` for Camoufox)
- [ ] tags include the genre keywords scoring formula needs
- [ ] `tier` is `B` for new, unproven sites
- [ ] SKILL.md table updated with matching site IDs
- [ ] Also sync `SKILL.md` to music-record repo (not just sites.json)