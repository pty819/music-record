# 2026-10-18 Camoufox → Chromium

## 背景

管道原本有两处硬依赖 Camoufox（Firefox 内核的反自动化浏览器）：

1. 3 个 HTML 抓取脚本通过 REST 服务 `http://127.0.0.1:9377` 驱动它：
   `scrape_musique_machine.py`、`scrape_all_about_jazz.py`、`scrape_mixmag_asia.py`
2. 5 个探索站由 kanban worker 用它做 JS 渲染

迁移到 amer1（Hermes 所在主机）时，Camoufox 是唯一搬不过来的东西——需要额外下载约 400MB 浏览器二进制 + 一个 systemd user unit（`hermes-camoufox.service`）。而 Hermes 本身已经自带 Chromium（`~/.hermes/tools/chromium-*/chrome-linux64/chrome`）。

决定：去掉 Camoufox，用自带 Chromium 走 CDP。

## 新增 bin/chromium_browser.py

Chrome DevTools Protocol 客户端 + 一个与 Camoufox REST **同形**的接口层。

```
POST   /tabs                {userId, sessionKey, url} → {tabId}
POST   /tabs/{id}/navigate  {url}                     → {success, tabId}
POST   /tabs/{id}/evaluate  {expression}              → {result}
POST   /tabs/{id}/content   {}                        → {html}
DELETE /tabs/{id}                                     → {closed}
```

两种接法：

| 方式 | 用法 | 适用 |
|---|---|---|
| 进程内 | `from chromium_browser import LocalApiClient` | **抓取脚本用这个**，无端口、无守护进程 |
| REST 服务 | `python3 bin/chromium_browser.py --serve --port 9377` | 临时跑、或外部脚本需要 HTTP |
| 便捷函数 | `fetch(url)` / `evaluate(url, js)` | 探针、一次性诊断 |

自检：`python3 bin/chromium_browser.py --self-check`

## 脚本改动（3 个，各只改 `_api` 实现）

`CAMOFOX_BASE = "http://127.0.0.1:9377"` 删掉，`_api()` 函数体换成一行
`return _CHROME.call(method, path, body)`。**JS 提取逻辑一行没动**——因为契约同形。

## 踩过的三个坑

### 1. CDP 握手 403

```
WebSocketBadStatusException: Handshake status 403 Forbidden
Rejected an incoming WebSocket connection from the http://127.0.0.1:28205 origin.
```

Chrome ≥111 默认拒绝带非空 Origin 的 WebSocket 握手，而 `websocket-client` 会带 Origin 头。

**修**：Chromium 启动参数加 `--remote-allow-origins=*`。

### 2. `Page.enable` 报 -32601

```
CDP Page.enable 失败: {'code': -32601, 'message': "'Page.enable' wasn't found"}
```

`Page` / `Runtime` 域是 **per-target** 的，browser 级 WebSocket 连接上根本没有这些方法。

**修**：启动时先 `Target.createTarget` → `Target.attachToTarget` 拿到 `sessionId`，之后所有 Page/Runtime 调用都带 `sessionId`。`open_tab()` 同样要先 attach 再 navigate。

### 3. `/evaluate` 返回函数对象而不是结果

musique_machine 抓取跑通但 **0 条**。它的 `EXTRACT_REVIEWS_JS` 写的是裸函数：

```js
() => { const results = []; ...; return results; }
```

Camoufox 的 `/evaluate` 对函数表达式会**自动调用一次**，直接求值只会拿到函数对象本身。

**修**：`chromium_browser.py:_invoke_if_function()` 识别三种写法并包成 IIFE ——
`() => {}` / `async () => {}` / `function(){...}` / `function foo(){...}` / 裸 `return ...`。
已验证 8 种输入的包装结果正确。

## 能力对比（2026-10-18 实测）

| 站 | 结果 |
|---|---|
| musique_machine | ✅ 36.6s，提取到真实乐评（artist/album/score/body） |
| point_of_departure | ✅ 36.1s |
| resident_advisor | ✅ 36.2s |
| **boomkat** | ⚠️ `document.title` = `"Just a moment..."`，CF Turnstile 没过 |
| all_about_jazz | ❌ `Runtime.evaluate` 超时（未定位，待查） |

**Chromium 能替代 JS 渲染，不能替代反检测指纹。** Boomkat 这类 Turnstile 站要走空结果协议写 0 条；要恢复得换出口 IP（见 `mihomo-proxy-management` skill 的 exit-IP reputation gate），不是换浏览器。

## 副作用：没有守护进程了

原来 9377 端口常驻一个浏览器进程，现在每次抓取现场起 Chromium、用完就退。好处是彻底去掉一个 systemd unit 和 400MB 二进制；代价是每次开 tab 有 ~5-8s 启动开销，且并发上限由 `scrape_html_parallel.py` 的进程并行决定（不再受浏览器实例数限制）。

## 顺带修的真 bug：provider_failover.py

`messages.create(temperature=0.7)` 在 anthropic SDK ≥1.0 已把该参数移出签名，调用直接 TypeError，评分全灭（Pi 上装的是旧版所以一直没暴露）。

**修**：删掉 `temperature`，在**最新 SDK（1.15.0）**上验证通过。不是靠钉旧版本绕过去。
验证：4 条样本 `4/4 成功`，`provider 统计 {"minimax": {"ok": 5, "fail": 0}}`。
