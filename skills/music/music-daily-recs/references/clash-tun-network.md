# Clash TUN 网络干扰排查

## 环境

- **Clash Verge Rev**（`/usr/bin/clash-verge-service` + `/usr/bin/clash-verge`）
- TUN 模式：`enable: true`, `stack: gvisor`, `auto-route: true`, `strict-route: false`
- 配置路径：`~/.local/share/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml`
- mixed-port：7897（TUN 启用时代理端口通常也不通）
- 其他监听端口：33331（clash API）

## 症状

| 操作 | 错误 |
|---|---|
| `git push` (SSH) | `Connection closed by 28.0.0.22 port 22` |
| `git push` (HTTPS) | `gnutls_handshake() failed: The TLS connection was non-properly terminated` |
| `curl https://github.com` | `OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to github.com:443` |
| `curl https://api.github.com` | 空响应，exit code 0 |

注意：`https://www.google.com` 可能仍然通（200），不代表 GitHub 也通。

## 诊断命令

```bash
# 1. 确认 Clash 进程
pgrep -a clash

# 2. 确认 TUN 状态
grep -A5 "tun:" ~/.local/share/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml

# 3. 测试 GitHub 连通性
curl -v --max-time 10 https://github.com 2>&1 | tail -10

# 4. 检查端口占用
ss -tlnp | grep -E "7897|33331"
```

## 处理方案

1. **用户手动关 TUN** → push → 重开（最可靠）
2. **切 HTTPS remote** → 但 TUN 拦截 HTTPS 同样失败
3. **走 mixed-port 代理** → TUN 启用时代理端口不可靠（测试 7897 返回 000）
4. **如果本地已提交且不紧急** → 跳过 push，下次 TUN 关闭时补推

## 与 cloudflared 的区别

之前的 SKILL.md 把 SSH 失败归因于 cloudflared（28.0.0.22 是 cloudflared 隧道 IP）。实际上 cloudflared 只影响 SSH 端口 22 的流量重定向，但 Clash TUN 在网络层拦截所有出站流量，包括 HTTPS 443。两者可能同时存在，但 HTTPS 也失败时，根源是 Clash TUN。
