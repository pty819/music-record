# Camoufox Configuration for Anti-Blocking — Python Server + systemd

## 2026-05-19 重大升级

从 Node.js 版 `@askjo/camofox-browser` 切换到 **Python 独立 HTTP REST 服务器**（`camoufox_server.py`），通过用户级 systemd 服务实现开机自启。

**动机**：`camoufox-js` npm 包在 ARM64（Rockchip）上缺失 `impit-linux-arm64-gnu` 原生模块。Python 版 `camoufox` 包（通过 Playwright 控制 Camoufox 浏览器）兼容性好。

## 架构

```
systemd user service → camoufox_server.py (port 9377) → Camoufox binary (~/.cache/camoufox/)
                                        ↑
                              Hermes via CAMOFOX_URL
```

## 服务管理

```bash
# 用户级 systemd 服务（非 root）
loginctl enable-linger liyifan
systemctl --user daemon-reload
systemctl --user enable ~/camofox-browser/hermes-camoufox.service
systemctl --user start hermes-camoufox.service
systemctl --user status hermes-camoufox.service
```

## Hermes 配置

```yaml
browser:
  engine: auto
  camofox:
    url: http://localhost:9377
```

```
CAMOFOX_URL=http://localhost:9377
```

## REST API 端点（测试站点可达性用）

Camoufox server 使用 **tab-based API**，不是简单的 /fetch。测试流程：

```python
import requests
CAMOFOX = 'http://localhost:9377'

# 1. 创建 tab（同时导航到 URL）
r = requests.post(f'{CAMOFOX}/tabs', json={
    'userId': 'test-user',
    'sessionKey': 'test-session',
    'url': 'https://example.com/'
}, timeout=30)
tid = r.json()['tabId']

# 2. 获取页面快照
r2 = requests.get(f'{CAMOFOX}/tabs/{tid}/snapshot', timeout=15)
text = r2.json().get('text', '')[:500]

# 3. 关闭 tab
requests.delete(f'{CAMOFOX}/tabs/{tid}', timeout=5)
```

### 端点列表

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/health` | 服务状态 |
| POST | `/tabs` | 创建 tab（可带 url 参数自动导航） |
| GET | `/tabs/{id}` | tab 信息 |
| GET | `/tabs/{id}/snapshot` | 页面文本快照 |
| GET | `/tabs/{id}/screenshot` | 页面截图 |
| POST | `/tabs/{id}/navigate` | 导航到新 URL |
| POST | `/tabs/{id}/click` | 点击元素 |
| POST | `/tabs/{id}/type` | 输入文本 |
| POST | `/tabs/{id}/scroll` | 滚动页面 |
| POST | `/tabs/{id}/evaluate` | 执行 JS |
| DELETE | `/tabs/{id}` | 关闭 tab |

### 常见错误

| 错误 | 含义 |
|------|------|
| `NS_ERROR_NET_INTERRUPT` | 网络层连接被中断（SSL/TLS 握手失败，非浏览器兼容性问题） |
| `NS_ERROR_CONNECTION_REFUSED` | 目标服务器拒绝连接 |
| `timeout` | 页面加载超时（默认 30s） |

## 已知限制

- `browser_click` 可能超时（30s timeout），优先用 `browser_navigate`
- `browser_console` JS evaluation 不支持

## 实测 Cloudflare 穿越效果

| 站点 | Camoufox 结果 |
|------|--------------|
| Boomkat (ASN 黑名单) | ✅ 可绕过 |
| RA 详情页 (Cloudflare 403) | ❌ |
| AAJ 详情页 (Cloudflare 防护) | ❌ |
| ProgArchives (JS 挑战) | ❌ |
