# Camofox 配置（本机现状）

> 旧的 Python 单文件服务（`camoufox_server.py`）随 Pi 迁移已下线，**不要再按那套部署**。当前形态是 npm 包 + system 级 systemd 服务，完整配方见 `references/camofox-backend.md`。

## 当前架构

```
camofox.service (systemd, system 级)
    ↓
/opt/camofox/node_modules/@askjo/camofox-browser/server.js
    ↓
Camoufox 引擎 → /root/.cache/camoufox/  (~1.3GB)
```

REST 监听 `127.0.0.1:9377`（只绑回环）。

## 服务管理

```bash
systemctl status camofox          # active + enabled
systemctl restart camofox          # 改完环境变量后必须 restart
curl -s http://127.0.0.1:9377/health
```

`/health` 返回 `{"ok":true,"engine":"camoufox","browserConnected":true,"browserRunning":true,"activeTabs":N,"activeSessions":N}`。

`activeTabs` / `activeSessions` 不回零会吃掉内存（建 tab 要 fork ~230MB 的 Firefox 进程），必要时清：

```bash
curl -s "http://127.0.0.1:9377/tabs?userId=<id>"   # 列出
curl -s -X DELETE "http://127.0.0.1:9377/tabs/<tabId>?userId=<id>"
```

## Hermes 接线

```
~/.hermes/.env          CAMOFOX_URL=http://127.0.0.1:9377
~/.hermes/config.yaml   browser.cloud_provider: camofox
                         browser.camofox.managed_persistence: true
```

改完**重启 gateway** 才生效。

## 端点

| 方法 | 路径 | userId 位置 | 用途 |
|---|---|---|---|
| GET | `/health` | — | 健康检查 |
| POST | `/tabs` | body | 建 tab（body 需 `userId` + `sessionKey` + `url`）|
| GET | `/tabs` | query | 列出 tab |
| GET | `/tabs/{id}/snapshot` | **query** | 页面快照 |
| POST | `/tabs/{id}/evaluate` | **body** | 执行 JS（只接受表达式）|
| POST | `/tabs/{id}/navigate` | **body** | 导航 |
| POST | `/tabs/{id}/click` / `type` / `press` / `scroll` | body | 交互 |
| DELETE | `/tabs/{id}` | query 或 body | 关 tab |

**GET 路由只认 query string，POST 路由只认 body** —— 放错位置就是 `400 userId required`。

## 常见错误

| 错误 | 含义 | 处理 |
|---|---|---|
| `500 tab create timed out after 30000ms` | 内存不足，fork Firefox 超时 | 清掉自己名下的旧 tab 再重试；客户端已内置重试 |
| `400 userId required` | userId 放错了位置 | GET → query，POST → body |
| `evaluate` 返回无 `result` 字段 | 传了裸函数体 `() => {...}` | 包成 IIFE：`(() => {...})()` |
| `navigate failed ... Timeout 30000ms` | 服务端导航超时（默认 30s）| `NAVIGATE_TIMEOUT_MS=60000` |
| `xvfb not available, falling back to headless` | 缺 Xvfb | 装 Xvfb；headless 下指纹伪装打折 |

## 实测 Cloudflare 穿越效果（Camofox）

| 站点 | 结果 |
|---|---|
| residentadvisor.net | ✅ 无拦截 |
| allaboutjazz.com | ✅ 列表页正常（`rows=16`）|
| pointofdeparture.com | ✅ curl 被拒但浏览器能过 |
| boomkat.com | ⚠️ Turnstile 挑战页（`Just a moment...`），按空结果协议早退 |
| thewildcity.com | ❌ 站点对出口 IP 不响应（TCP 通、HTTP 不返回），浏览器与代理均超时 |
