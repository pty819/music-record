# 浏览器层：Camofox（主） + Chromium/CDP（备选）

## 架构

抓取脚本**不自己起浏览器**，只打一个常驻服务的 REST 接口：

```
脚本 (camofox_client.CamofoxClient)
    ↓  HTTP 127.0.0.1:9377
camofox.service  →  @askjo/camofox-browser (npm)  →  Camoufox (Firefox fork, 反检测)
```

Camofox 是**一个常驻实例服务所有站**，不是每脚本拉一个浏览器——这是它比旧 Chromium/CDP 方案更省内存的原因（1.6GB 的机器上常驻约 600MB，而单个 Chromium 站会拉起 ~74 个子进程、RSS 冲到 935MB）。

## `bin/camofox_client.py`

与旧 `chromium_browser.LocalApiClient` **完全同形**的客户端，接口刻意做成一样，所以换后端时脚本只需改 import + 实例化：

```python
from camofox_client import CamofoxClient

_CHROME = CamofoxClient(user_id="scraper_all_about_jazz",
                        session_key="session_aaj", settle=4.0, timeout=150)

def _api(method, path, body=None):
    if method == "POST" and path.rstrip("/") == "/tabs":
        return _CHROME.open_tab((body or {}).get("url", "about:blank"))
    return _CHROME.call(method, path, body)
```

`user_id` 按站点分开：Camofox 按 userId 隔离会话与 cookie/profile，混用会让 cookie 串味。

### 三处契约差异（Camofox ≠ Chromium/CDP）

**这三条是换后端后最容易踩的坑，且都表现为「静默拿到 None」而不是报错。** `camofox_client.py` 已在客户端层做兼容，脚本侧无感；自己写新调用方时必须知道：

| | Chromium/CDP | Camofox | 踩中时的症状 |
|---|---|---|---|
| `evaluate` 入参 | 接受裸函数体 `() => {...}` | **只接受表达式** | 传裸函数体 → 返回 `{"ok": true}` 但**没有 `result` 字段** → 调用方拿到 `None` → 脚本安静地 0 条 |
| `userId` 位置 | 不区分 | GET 路由**只认 query string**，POST 路由**只认 body** | 放错位置 → `400 userId required` |
| 建 tab | 起一个 Chromium 子进程 | **fork 一个 Firefox 进程（~230MB）** | 内存紧张 → `500 tab create timed out after 30000ms`（服务端 30s 硬上限） |

第一条尤其阴险：Chromium 的 `Runtime.evaluate` 会把 `() => {...}` 当函数体执行，Camofox 不会。**验证方法**：直接调一次 `POST /tabs/:id/evaluate` 传裸函数体，看返回里有没有 `result` 键。

### 客户端已实现的健壮性

- **`open_tab()` 带重试**：失败时先关掉自己名下的残留 tab（`GET /tabs?userId=` → `DELETE`），等一拍让内存回收，再重试。建 tab 失败在 1.6GB 机器上是常态，不是 bug。
- **IIFE 包装**：客户端自动把 `() => {...}` 包成 `(() => {...})()`。
- **GET/POST 的 userId 分别注入 query / body**。
- **`wait_for_content()` 轮询**：不用固定 sleep 等待渲染（见下节）。
- **`navigate_fast()` 快速导航**：绕开服务端 `/navigate` 端点的 commit 等待（见下节）。

### `navigate_fast()`：最大的性能杠杆

Camofox 的 `POST /tabs/:id/navigate` 内部是：

```js
await page.goto(url, { waitUntil: 'commit', timeout });
await page.waitForLoadState('domcontentloaded', { timeout });
```

`commit` 意味着**等 Cloudflare 挑战走完才返回**。实测 CF 站上 **17-36 秒一篇**——这是 Camofox 站跑不完管道的真正原因，不是站点慢。

改成在页面里改 `location.href`：

```python
client.navigate_fast(tab_id, url)   # evaluate 里执行 window.location.href = url
```

`evaluate` 立刻返回（~0.4s），CF 挑战在后台继续。

### ⚠️ 但必须同时验证 URL 切换了 —— 否则抓到的是上一篇的正文

`navigate_fast` 是「起飞即返」：**evaluate 返回时浏览器还在飞，页面仍停留在上一篇**。此时按「body 长度 > N」轮询正文，**上一篇的正文已经满足长度条件**，于是抓到了上一篇文章的内容。

实测症状极隐蔽：URL 和 excerpt 各不相同、条数正常、报告看着正常，**只有 body 是错的**（mixmag 21 条里 13 条 body 完全相同，内容是别的文章的正文）。评分靠 excerpt 仍能出分，所以整条管道不会报错。

规则：**`navigate_fast()` 之后必须用 `wait_for_page()` 取正文**，它一次 evaluate 同时取 `{url, body}`，URL 匹配且正文够长才算成功：

```python
from camofox_client import wait_for_page

body, ok = wait_for_page(
    client, tab_id, url, BODY_EXPR,   # BODY_EXPR 必须返回字符串的表达式
    attempts=25, delay=0.4, body_min=200,
)
if not ok:
    ...  # URL 没在 attempts 内切换 → 丢弃本篇，别用旧正文
```

`BODY_EXPR` 必须是**返回字符串的完整表达式**（`(() => {...})()`），不是裸函数体——`wait_for_page` 要把它内嵌进自己的 JSON 打包表达式里。裸 `() => {...}` 内嵌后语法不成立，且 Camofox 的 evaluate 本来就只认表达式。

### 为什么必须是「一次 evaluate」而不是「先等 URL 再等正文」

导航期间 Camofox 的 evaluate 要等 **~1.6s 才回 `409 Conflict`**。分两轮做（先 `wait_for_navigation()` 轮询 URL，再 `wait_for_content()` 轮询正文）意味着每篇跑两串 evaluate 序列：

| 做法 | mixmag_asia 耗时 | 结果 |
|---|---|---|
| 不检查 URL（只等正文长度） | 57.9s | ❌ 快但正文全错 |
| 分两轮（等 URL + 等正文） | 217.6s | ❌ 正确但超过 180s per-site timeout，会被砍 |
| **`wait_for_page()` 一次取两者** | **104.4s** | ✅ 正确且在 timeout 内 |

`wait_for_navigation()` 作为底层积木保留在客户端里，但**脚本侧一律用 `wait_for_page()`**——省掉一整串 evaluate 序列。

| 站 | `/navigate` | `navigate_fast()` + `wait_for_page()` | 条数 |
|---|---|---|---|
| mixmag_asia | 600s 超时（只到 13/25） | **104.4s** | 21-25 |
| all_about_jazz | 187-420s | **89.3s** | 6-9 |
| musique_machine | 33.7s | **11.0s** | 0-1 |

规则：**Camofox 站一律用 `navigate_fast()` + `wait_for_page()`，不用 `/navigate` 端点，也不用「只等正文长度」的裸轮询。** `/navigate` 端点只在需要服务端确认导航结果（HTTP 状态、最终 URL）时才值得。

### 验证正文真来自这一篇：统计 body 唯一性，不要只看条数

抓完一批之后，**「条数对」不等于「内容对」**。跨文章重复的 body 靠肉眼看条目列表发现不了（URL 和 excerpt 都不同），必须统计正文本身的重复度。

```python
import collections
bodies = [i.get("body") or "" for i in items]
dup = [(len(b), n) for b, n in collections.Counter(bodies).items() if n > 1]
print("重复组:", len(dup), "空 body:", sum(1 for b in bodies if not b.strip()))
```

判据：**重复组应为 0**。长度分布成片重复（2276×6、2972×4）= 抓到的是残留正文；分布连续（1499、1864、2024、2063…）= 正常。

配套检查「URL 与正文是否对应」——两条 URL 不同、body 完全相同，且那段 body 的开头是**另一篇文章的标题**，即可确诊。

这条检查要进常规验收步骤，不只是调试时用：错 body 的失败形态是「exit 0、条数正常、报告正常」，任何靠「跑通了」判断的验收都会放过它。

### `wait_for_content()`：不要用固定 sleep 等渲染

固定 `time.sleep(1.2/2/3)` 是给 Chromium/CDP 定的节奏。Camofox 走真实 Firefox 网络栈，CF 站更慢，固定等待会在正文渲染完前提取 → **正文为空**。症状很隐蔽：脚本 exit 0、无报错，只是某几篇 body 是 0 字符。

```python
wait_for_content(client, tab_id, expr, attempts=12, delay=1.0, predicate=None)
```

`predicate` 用于「非空不够」的场景（如 HTML 要 > 5000 字符才算渲染完）。

### 探针必须用脚本自己的 client —— 否则结论是假的

调脚本模块里的函数时，**必须用脚本模块里那个 client 实例**（同一个 `user_id`），不能自己 new 一个。Camofox 按 `userId` 隔离会话，**另一个 user_id 看不到这个 tab**。

失败的探针：

```python
c = CamofoxClient(user_id="probe_mm")   # ← 自己的 client
tab = c.open_tab(url)
arts = m.extract_articles(tab["tabId"])  # m._CHROME 看不到这个 tab → 0 篇
```

正确的探针：

```python
tab = m._CHROME.open_tab(url)            # ← 用脚本自己的 client
arts = m.extract_articles(tab["tabId"])
```

这个坑的表现是「同一个页面，手动 evaluate 明明有 21 篇，脚本就是 0 篇」——**会让你误判成选择器坏了或后端坏了，转而去改不相关的东西**。先确认探针和被测代码用同一个 client，再怀疑别的。

### 服务端日志：`409` 不是错误，是「导航中，evaluate 请稍后」

服务端在导航期间对 evaluate 回 **`409 Conflict`**（耗时 ~1.6s），而不是快速失败。客户端必须把它当成「还没到」继续轮询，**不能当成异常抛出去**——否则每次导航都会抛错。

日志里判断某站是否真的用了浏览器，看 `msg=req` 的 `userId` 分布：

```bash
journalctl -u camofox --no-pager | grep '"msg":"req"' | grep -oE '"userId":"[^"]*"' | sort | uniq -c
```

`userId` 就是站点标识（`scraper_mixmag_asia` 等），按它归类能直接回答「今天到底哪些站走了浏览器」。⚠️ `journalctl --since 'today HH:MM'` 在这台机上会返回空，改用 `journalctl -u camofox` 拉全量再 grep。

⚠️ **`pkill -f '<pattern>'` 的 pattern 会匹配到调用它的那条命令本身**——pkill 扫描整个进程表，而你的 shell 的 argv 里就含着这个 pattern。实测 `pkill -f 'timeout 900 python3 bin/daily_pipeline.py'` 把自己所在的进程组一起杀了，正在跑的评分层被误杀。

规则：**要停某个后台任务，用 `process_manage`（按 session id）或先 `ps` 拿到确切 PID 再 `kill <pid>`**，不要用 `pkill -f`。确实要用 pkill 时，pattern 写成不可能匹配自己命令行的形式（如用字符类 `[p]ython3`）。

### 选择器要按「最长容器」选，不要按标签名选

`<article>` 标签存在 ≠ 它装着正文。实测 mixmag 的 `<article>` 只有 211 字符（是侧栏/摘要容器），真正的正文在 `<main>`（4248 字符）。

规则：**候选多个容器，按 innerText 长度挑最大的**，而不是按标签名优先。

```js
const pick = (el) => el && el.innerText ? el.innerText : '';
const candidates = [
    pick(document.querySelector('main')),
    pick(document.querySelector('article')),
    pick(document.querySelector('.article-body')),
    pick(document.querySelector('.post-content')),
    pick(document.querySelector('.entry-content')),
    pick(document.body),
].filter(t => t && t.length > 200);
return candidates.sort((a, b) => b.length - a.length)[0].slice(0, 10000);
```

### 日期过滤器静默失效 = 你在无边界地爬

`if pub_date and pub_date < cutoff: continue` 这类写法，**`pub_date` 为空时不会跳过，而是放行**。当列表页根本不提供日期字段时，`parse_date()` 恒返回 `None`，过滤器等于不存在——每一篇都进正文抓取。

实测：mixmag 列表页与文章页都没有日期（DOM 里无 `time` 元素、正文里无日期串），于是 25 篇全部被抓，而 `--days 1.5` 一个也没筛掉。**症状是“明明只要 1.5 天，怎么跑了 25 篇”。**

规则：

- **先证明日期字段真的存在**，再相信日期过滤。探针要分别检查列表页和文章页：DOM 里有没有 `time` 元素、正文里有没有日期串。
- 若站点不给日期，**用文章发布日期自己判**（从文章页拿），而不是把过滤条件当成已生效。
- 抓取量失控时的正确反应是**限制抓取篇数**（取列表前 N 篇），而不是调大 `--days` —— `--days` 在无日期字段时是无效旋钮。

### 列表页选择器要覆盖真实的文章路径

旧选择器 `a[href*="/music/"]` 仍能匹配，但 `/music/` 现在只是栏目标录，文章搬到 `/read/` 和 `/feature/`。**轮询等页面就绪时用的选择器必须和提取用的选择器一致**，否则会永远等不到（实测 `a[href*="/music/"]` 命中数不为 0 但永远不涨，轮询空转到超时）。

用「链接总数从 108 涨到 112」这类**增量信号**判断渲染完成，而不是等某个固定数量。


### 自检

```bash
cd /home/liyifan/music-record
.venv/bin/python3 bin/camofox_client.py --url https://example.com
```

验收要打**真实的 Cloudflare 站**：`example.com` 在任何后端都能过，证明不了任何东西。

## 部署（camofox.service）

```bash
systemctl status camofox        # active + enabled
curl -s http://127.0.0.1:9377/health
# {"ok":true,"engine":"camoufox","browserConnected":true,"browserRunning":true,...}
```

unit 要点（`/etc/systemd/system/camofox.service`）：

- `CAMOFOX_PORT=9377`、`CAMOFOX_BIND_HOST=127.0.0.1`（只监听回环）
- `MemoryMax=900M` / `MemoryHigh=700M` —— Camoufox 是 Firefox 内核，不设上限会把这台机器推进 swap
- `KillSignal=SIGTERM` + `TimeoutStopSec=90` —— cookie 只在优雅退出时 checkpoint，`kill -9` 会丢登录态
- **`NAVIGATE_TIMEOUT_MS=60000` / `HANDLER_TIMEOUT_MS=60000`** —— 默认 30000 对 CF 站文章页不够（页面懒加载，到不了 Playwright 的 `commit`），navigate 会 500
- **需要 Xvfb**：缺 Xvfb 时 Camofox 会 `xvfb not available, falling back to headless`，而 headless 下指纹伪装打折——正是选 Camofox 的理由。日志里应出现 `xvfb virtual display started`

## Hermes 侧接线

```
~/.hermes/.env          CAMOFOX_URL=http://127.0.0.1:9377
~/.hermes/config.yaml   browser.cloud_provider: camofox
                         browser.camofox.managed_persistence: true
```

`browser.cloud_provider` 不是 `hermes config set` 认识的 schema 键（会警告 "not a recognized config key"）——**运行时确实读它**（`tools/tool_backend_helpers.py` 的 `_SELECTION_NAME_KEYS = {"browser": ("cloud_provider",)}`），用 `read_selection("browser")` 验证，别因为警告就回退。

改完要**重启 gateway** 才生效（重启只能在 gateway 进程外面做）。

## 备选后端：Chromium/CDP

旧 Chromium CDP 客户端 `bin/chromium_browser.py` 已于 2026-10-27 删除。

它实现了同形的 REST 契约（`POST /tabs`、`/tabs/{id}/navigate`、`/tabs/{id}/evaluate`、`/tabs/{id}/content`、`DELETE /tabs/{id}`），三种用法：进程内 `LocalApiClient`、`--serve --port 9377`（**会与 Camofox 抢 9377，别同时开**）、模块级 `fetch()` / `evaluate()`。

CDP 自身的坑（403 握手、per-target 域、函数表达式、`atexit` 清理、navigate 复用 target、OOM 与内存上限、后台任务轮询）看 `headless-browser-scraping` skill。

## 选型：什么时候用哪个

**Chromium 能渲染 JS，但没有反检测指纹。** 纯 JS 渲染站两个都行；**Cloudflare 站只有 Camofox 有意义**——Chromium 更容易被识别成机器人。

判断依据不是「需要浏览器」，而是「这站会不会拦自动化」：先按 `references/site-investigation-methodology.md` 找免浏览器的路子（真 RSS > 服务端渲染 > 浏览器），确实没有再上浏览器。

## 站点级实测

| 站 | 后端 | 结果 |
|---|---|---|
| all_about_jazz | Camofox | ✅ 12 条，含全文正文（`navigate_fast` 后 ~53s） |
| mixmag_asia | Camofox | ✅ 25 篇正文（`navigate_fast` 后 ~58s） |
| musique_machine | Camofox | ✅ 1 篇（~19s） |
| point_of_departure | Camofox | ✅ 10 条 |
| resident_advisor | Camofox | ✅ 无 CF 拦截 |
| boomkat | Camofox | ⚠️ CF Turnstile：`document.title` 返回 `Just a moment...`，按空结果协议早退，禁止反复开 tab |
| **wild_city**（已删 2026-10-27） | - | ❌ 站点侧不可达：TCP 443 连得上但 HTTP 不返回。得换出口 IP 或放弃——已放弃并删除站点与全部脚本 |

**「curl 失败但浏览器能过」和「浏览器也过不了」是两回事**：前者是 TLS/SNI 指纹被拒（浏览器能救），后者是站点对出口 IP 不响应（浏览器也救不了）。分不清就会白折腾后端。

## 选择器腐化会伪装成「后端坏了」

换后端后 `all_about_jazz` 一度跑出 0 条，但 CF 其实过了（手动 evaluate 拿到 `rows=16`）。真因是**页面结构变了**：`span.small` 已经不存在（查到 0 个），日期挪到了 `.data-row-content` 的 innerText 里（`Published on October 27, 2026`），旧选择器取不到日期 → 全部条目被当成「无日期」丢弃。

**排查顺序**：先证明后端能过（手动 evaluate 拿行数），再查选择器，最后才调后端。行数对但条数为 0 = 选择器问题；行数本身为 0 = 后端问题。

## 出货路径的浏览器约束

本机 1.6GB RAM。**旧结论是「出货路径必须完全无浏览器」**，依据是单个 Chromium 站会拉起 ~74 个子进程、RSS 冲到 935MB，可用内存掉到 137MB，内核 OOM killer 静默杀掉 chrome。

**这个结论只对「每站拉起一个浏览器」的后端成立。** Camofox 是常驻服务（一个 Firefox 实例服务所有站），不再每站拉浏览器，所以 all_about_jazz / mixmag_asia / musique_machine 已放回 `SCRIPTS`。

失败形态很有欺骗性：**`empty stdout` + 0 条，stderr 无异常，进程消失得干干净净**。看日志只会以为“该站没更新”，不会想到是内存。

```bash
dmesg -T | grep "Killed process" | tail -3    # 唯一的现场
```

已试过且**均无效**，不要再重复：降 V8 heap（已到下限）、Chromium 站串行化（串行照样被杀）、换机器扛（另一台机上 chrome 渲染同样挂死）。

三条 Camofox 站的硬约束：

1. **Camofox 站之间必须串行** —— 并发开 3 个 tab 全部建失败（fork Firefox 时内存不足，available 掉到 387MB）。`scrape_html_parallel.py` 拆成两批：纯 HTTP 站全并发，Camofox 站在其后串行。
2. **Camofox 站要单独给 timeout** —— `SCRIPTS` 元组第 4 个元素是 per-site timeout 覆盖值。
3. **CDP 后端已退役** —— `SCRIPTS` 里不应出现任何 `import chromium_browser` 的条目。

```bash
sed -n '/^SCRIPTS = \[/,/^\]/p' bin/scrape_html_parallel.py | grep -c 'chromium_browser'   # 期望 0
```

## 选择器 rot：非零行数也可能全是导航

`mixmag_asia` 曾返回 8 条、exit 0、无 error——每条“文章”都是栏目名（`Reviews`、`New Releases`）。旧选择器 `a[href*="/music/"]` 仍匹配，但 `/music/` 现在只是栏目标录，文章搬到了 `/feature/` 和 `/read/`。

规则：

- 打印前几条提取出来的标题和 URL。栏目名一眼可辨，行数不是证据。
- 栏目标录与文章共用前缀时，按路径深度过滤：`new URL(url).pathname.split('/').filter(Boolean).length < 3`。
- 新文章前缀加成分支选择器，别放宽旧选择器——放宽会把导航重新纳入。

## 运行管道时的环境：子进程用 `sys.executable`，不要硬编码 `python3`

`scrape_html_parallel.py` 原来把每个 scraper 作为裸 `python3` 拉起，依赖**调用方的 PATH** 里有正确的 venv。直接跑管道时子进程落到系统 Python，缺 bs4/feedparser，4 个站静默失败（`empty stdout (rc=1)` + `ModuleNotFoundError`）——**看起来像 scraper 自己的 bug**。

修法：`cmd = ["timeout", str(eff_timeout), sys.executable, script_path, ...]`。无论谁调、用什么解释器启动管道，子脚本都用同一个解释器。

**验证要看每个站的错误数，不是只看管道退出码。** 修前 4 个站报 `empty stdout (rc=1) ModuleNotFoundError: No module named 'bs4'`，修后同样 4 个站 `0 errors`：

```bash
# 管道 stderr 里逐站列出 ✅ / ❌，直接数 ❌ 的行数
.venv/bin/python3 bin/scrape_html_parallel.py --out-dir /tmp/t --days 1.5 2>&1 | grep -c '❌'   # 期望 0
```

（历史）已删除的 `chromium_browser.py` 曾需要 `websocket-client`，系统 python 没有——这也是它退役的原因之一。

## 评分：永远不要靠降级 SDK 版本绕过签名变化

`provider_failover.py` 曾给 `messages.create()` 传 `temperature=0.7`，而 anthropic SDK 在 1.0 移除了该参数 → 每次评分调用抛 `TypeError`，当天报告零评分。生产机因为钉着旧 SDK 从未暴露——这个 bug 只在装当前版本的机器上现形。修法是**删掉该参数并用最新 SDK 验证**，不是钉一个能掩盖问题的旧版本。

两点踩坑：

- `tests/fakeanth/` 里的假 SDK 把 `temperature` 声明成**必填位置参数**，于是删掉调用点的参数反而让 8 个测试以困惑的「0 calls」失败而不是有用的 `TypeError`。测试替身必须用 `**kwargs` 吸收签名变化。
- 搬过目录的 checkout 里，陈旧的 `__pycache__` 仍指向旧的绝对路径，traceback 指向一个已不存在的目录。换了 checkout 路径后先删 `__pycache__` 再相信任何失败输出。
