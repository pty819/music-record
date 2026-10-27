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

`bin/chromium_browser.py` 保留为**备选后端与一次性排查工具**，不再是抓取脚本的默认路径。

它实现了同形的 REST 契约（`POST /tabs`、`/tabs/{id}/navigate`、`/tabs/{id}/evaluate`、`/tabs/{id}/content`、`DELETE /tabs/{id}`），三种用法：进程内 `LocalApiClient`、`--serve --port 9377`（**会与 Camofox 抢 9377，别同时开**）、模块级 `fetch()` / `evaluate()`。

CDP 自身的坑（403 握手、per-target 域、函数表达式、`atexit` 清理、navigate 复用 target、OOM 与内存上限、后台任务轮询）看 `headless-browser-scraping` skill。

## 选型：什么时候用哪个

**Chromium 能渲染 JS，但没有反检测指纹。** 纯 JS 渲染站两个都行；**Cloudflare 站只有 Camofox 有意义**——Chromium 更容易被识别成机器人。

判断依据不是「需要浏览器」，而是「这站会不会拦自动化」：先按 `references/site-investigation-methodology.md` 找免浏览器的路子（真 RSS > 服务端渲染 > 浏览器），确实没有再上浏览器。

## 站点级实测

| 站 | 后端 | 结果 |
|---|---|---|
| all_about_jazz | Camofox | ✅ 12 条，含全文正文 |
| mixmag_asia | Camofox | ✅ 抓 25 篇正文 |
| musique_machine | Camofox | ✅ 1 篇 |
| point_of_departure | Camofox | ✅ 10 条 |
| resident_advisor | Camofox | ✅ 无 CF 拦截 |
| boomkat | Camofox | ⚠️ CF Turnstile：`document.title` 返回 `Just a moment...`，按空结果协议早退，禁止反复开 tab |
| **wild_city** | 任意 | ❌ **站点侧不可达**：TCP 443 连得上但 HTTP 不返回（直连、代理、浏览器三种方式全超时）。不是浏览器问题——换后端救不了，得换出口 IP 或放弃这个站 |

**「curl 失败但浏览器能过」和「浏览器也过不了」是两回事**：前者是 TLS/SNI 指纹被拒（浏览器能救），后者是站点对出口 IP 不响应（浏览器也救不了）。分不清就会白折腾后端。

## 选择器腐化会伪装成「后端坏了」

换后端后 `all_about_jazz` 一度跑出 0 条，但 CF 其实过了（手动 evaluate 拿到 `rows=16`）。真因是**页面结构变了**：`span.small` 已经不存在（查到 0 个），日期挪到了 `.data-row-content` 的 innerText 里（`Published on October 27, 2026`），旧选择器取不到日期 → 全部条目被当成「无日期」丢弃。

**排查顺序**：先证明后端能过（手动 evaluate 拿行数），再查选择器，最后才调后端。行数对但条数为 0 = 选择器问题；行数本身为 0 = 后端问题。

## 出货路径必须无浏览器

本机 1.6GB RAM。单个 Chromium 站会拉起 ~74 个子进程、RSS 冲到 935MB，可用内存掉到 137MB，内核 OOM killer 静默杀掉 chrome。

失败形态具有欺骗性：**`empty stdout` + 0 条，stderr 无异常，进程消失得干干净净**。看日志只会以为“该站没更新”，不会想到是内存。

```bash
dmesg -T | grep "Killed process" | tail -3    # 唯一的现场
```

已试过且**均无效**，不要再重复：降 V8 heap（已到下限）、Chromium 站串行化（串行照样被杀）、换机器扛（另一台机上 chrome 渲染同样挂死）。

判定标准：`SCRIPTS` 里不应存在任何 `import chromium_browser` 或 `import camofox_client` 的条目。

```bash
sed -n '/^SCRIPTS = \[/,/^\]/p' bin/scrape_html_parallel.py | grep -cE 'chromium|camofox'   # 期望 0
```

## 选择器 rot：非零行数也可能全是导航

`mixmag_asia` 曾返回 8 条、exit 0、无 error——每条“文章”都是栏目名（`Reviews`、`New Releases`）。旧选择器 `a[href*="/music/"]` 仍匹配，但 `/music/` 现在只是栏目标录，文章搬到了 `/feature/` 和 `/read/`。

规则：

- 打印前几条提取出来的标题和 URL。栏目名一眼可辨，行数不是证据。
- 栏目标录与文章共用前缀时，按路径深度过滤：`new URL(url).pathname.split('/').filter(Boolean).length < 3`。
- 新文章前缀加成分支选择器，别放宽旧选择器——放宽会把导航重新纳入。

## 运行管道时的环境

`scrape_html_parallel.py` 把每个 scraper 作为裸 `python3` 拉起，所以 venv 必须在 PATH 最前，否则子进程死于 `ModuleNotFoundError: bs4`（而报错看起来像 scraper 自己的 bug）：

```bash
export PATH=/home/liyifan/music-record/.venv/bin:$PATH
```

`chromium_browser.py` 还需要 `websocket-client`，系统 python 没有。

## 评分：永远不要靠降级 SDK 版本绕过签名变化

`provider_failover.py` 曾给 `messages.create()` 传 `temperature=0.7`，而 anthropic SDK 在 1.0 移除了该参数 → 每次评分调用抛 `TypeError`，当天报告零评分。生产机因为钉着旧 SDK 从未暴露——这个 bug 只在装当前版本的机器上现形。修法是**删掉该参数并用最新 SDK 验证**，不是钉一个能掩盖问题的旧版本。

两点踩坑：

- `tests/fakeanth/` 里的假 SDK 把 `temperature` 声明成**必填位置参数**，于是删掉调用点的参数反而让 8 个测试以困惑的「0 calls」失败而不是有用的 `TypeError`。测试替身必须用 `**kwargs` 吸收签名变化。
- 搬过目录的 checkout 里，陈旧的 `__pycache__` 仍指向旧的绝对路径，traceback 指向一个已不存在的目录。换了 checkout 路径后先删 `__pycache__` 再相信任何失败输出。
