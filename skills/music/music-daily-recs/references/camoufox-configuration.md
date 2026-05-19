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
