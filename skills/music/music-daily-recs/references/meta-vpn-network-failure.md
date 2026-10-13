# Meta VPN 网络故障模式（2026-06-10）

## 症状

- 所有 12 个 HTML scraper 输出 0 字节文件（`scrape_html_parallel.py` 显示 `rc=1`）
- Camoufox server 返回 HTTP 500：`Page.goto: Timeout 30000ms exceeded`
- `curl https://...` 返回 `000` + `SSL_ERROR_SYSCALL`
- DNS 解析返回 `28.0.0.x` 假 IP（google → 28.0.0.91，github → 28.0.0.25）

## 根因

机器有 Meta VPN 接口（`28.0.0.1/30`，点对点隧道），默认路由走 Meta：

```
default via 28.0.0.2 dev Meta table 2022
```

Meta 接口的 DNS 服务器（28.0.0.2）返回假 IP，且 HTTPS 流量经 Meta 隧道转发失败。

## 诊断命令

```bash
# 1. 检查默认路由是否走 Meta
ip route get 8.8.8.8
# 正常: via 192.168.1.1 dev end0
# 异常: via 28.0.0.2 dev Meta

# 2. DNS 检查
python3 -c "import socket; print(socket.getaddrinfo('www.google.com', 443)[:1])"
# 正常: 142.250.x.x
# 异常: 28.0.0.x

# 3. HTTPS 连通性
curl -v --max-time 5 https://www.google.com 2>&1 | grep -E "SSL_ERROR|Trying|Connected"
```

## 关键发现

- **RSS 抓取不受影响**：`feedparser` 走的 HTTP 路径不同，部分 feed 仍能返回数据
- **git pull 可能受影响（2026-06-17 更新）**：SSH（28.0.0.28:22）和 HTTPS（gnutls_handshake 失败）均失败时，跳过 Step 1 即可。代码已在磁盘上，非阻塞
- **选择性 DNS 投毒（2026-06-17 新模式）**：不是所有 28.0.0.x 都失败——quietus/pitchfork 正常但 github/bandcamp 失败。判断标准：`curl -sL -o /dev/null -w "%{http_code}" --max-time 10 URL` 返回 000 = 该站不可达
- **Camoufox 服务本身正常**：`systemctl --user status hermes-camoufox` 显示 active，但浏览器内部导航超时
- **重启 Camoufox 无效**：问题在网络层，不在浏览器层

## 处理

1. **不要重启 Camoufox**——无效且耗时（deactivating 要 1-2 分钟）
2. 继续执行 Step 4-5（merge + kanban swarm 创建）
3. Camoufox worker 会在网络恢复后自动重试
4. 长期修复：调查 Meta VPN 为什么断连，或添加 `ip route` 备份规则

## 2026-06-10 实测时间线

| 时间 | 事件 |
|------|------|
| 04:04 | RSS 开始，120s timeout → 部分完成 |
| 04:08 | RSS 300s timeout → 部分完成 |
| 04:10 | RSS 600s timeout → 完成，4 items |
| 04:14 | HTML parallel 启动，12 scraper 全部 rc=1 |
| 04:18 | 发现 Meta VPN 问题，确认 curl 全部 000 |
| 04:22 | 尝试重启 Camoufox（无效，deactivating 耗时长） |
| 04:24 | 放弃修复网络，继续 merge + kanban swarm |
| 04:27 | Step 5 完成，swarm 创建成功 |

## 2026-06-17 选择性 DNS 投毒

| 站点 | DNS 结果 | curl 结果 | 说明 |
|------|----------|-----------|------|
| google.com | 28.0.0.x | 200 ✅ | 正常 |
| pitchfork.com | 28.0.0.154 | 200 ✅ | 正常 |
| thequietus.com | 28.0.0.155 | 200 ✅ | 正常 |
| github.com (SSH) | 28.0.0.28 | Connection closed by 28.0.0.28 port 22 | SSH 被阻断 |
| github.com (HTTPS) | 28.0.0.28 | gnutls_handshake() failed | TLS 被阻断 |
| daily.bandcamp.com | 28.0.0.45 | SSL_ERROR_SYSCALL | TLS 被阻断 |
| thewire.co.uk | 28.0.0.x | 301（正常 redirect） | 正常 |

**结论**：Meta VPN 对不同域名的转发策略不同。github.com 和 bandcamp 持续被阻断，其他站正常。

**处理**：跳过 git pull，RSS 68 条 + HTML 43 条 = 111 条正常产出，swarm 创建成功。
