# Synthesizer git push Pitfall — 2026-05-31 / 2026-06-01

## 问题

`recommend/{DATE}.md` 由 Synthesizer 生成并 commit 到本地，但 **GitHub 上不出现**。多次重复发生。

## 根因（2026-06-01 深入调查确认）

**不是 GFW/TLS 网络问题。** 实际错误是：

```
fatal: could not read Username for 'https://github.com': No such device or address
```

这是 **credential helper 认证失败**。具体机制：

1. git remote 用 HTTPS（`https://github.com/pty819/music-record.git`）
2. credential helper 配置为 `!/usr/bin/gh auth git-credential`
3. `gh auth git-credential get` 在手动测试中**正常工作**（返回 token）
4. 但在 kanban worker 的 Hermes agent 执行上下文中，credential helper **静默失败**
5. git 回退到从 stdin 读用户名 → 非交互环境 → `could not read Username`
6. SYNTHESIZER_BODY 指令 "如果 git push 失败（GFW），记录错误但继续下一步" **错误地将此归类为 GFW**

### 排除的假设

| 假设 | 验证 |
|------|------|
| GFW/TLS 网络封锁 | ❌ `git push --dry-run` 正常 |
| gh token 过期 | ❌ `curl` API 验证有效 |
| `fill` 操作不兼容 | ❌ git 2.43.0 用 `get`，gh 支持 |
| subprocess stdin 处理 | ❌ DEVNULL/PIPE/继承 三种模式全部通过 |
| 环境变量覆盖 | ❌ 无 GIT_TERMINAL_PROMPT / GIT_ASKPASS 设置 |

**未能在手动测试中复现精确的失败场景**，但 synthesizer 日志 (`t_325ae409.log` line 106) 确认错误确实是 `could not read Username`。

## 修复方案（推荐）

**把 remote 改成 SSH**，绕过 credential helper：

```bash
cd /home/liyifan/music-record
git remote set-url origin git@github.com:pty819/music-record.git
```

SSH key（`~/.ssh/id_ed25519`）已验证可用：`ssh -T git@github.com` 返回 `Hi pty819!`。

改完后 SYNTHESIZER_BODY 的 `git push origin main` 自动走 SSH，不再依赖 credential helper。

## SYNTHESIZER_BODY 需要同步修改

`kanban-swarm.py` 中的 SYNTHESIZER_BODY 当前写着：
```
如果 git push 失败（GFW），记录错误但继续下一步
```
这行**错误地标注了原因**，应改为：
```
如果 git push 失败，记录具体错误信息（区分 network / credential / auth），但继续下一步
```

## 教训

- **不要在 SYNTHESIZER_BODY 里预设失败原因**——"GFW"标签导致 agent 跳过真正的诊断
- 当 git push 在手动测试正常但在 agent 执行中失败时，优先检查 **credential helper** 和 **remote URL 协议**，而非假设网络问题
- HTTPS + `gh auth git-credential` 在 kanban worker 上下文中不可靠；SSH 是更稳定的方案
- 对于"生成文件 → 必须 push"这类关键步骤，push 后**必须验证** `git log --oneline origin/main..HEAD` 为空

## 更新：SSH 也会失败（2026-06-17）

即使 remote 已设为 SSH，当 Meta VPN 选择性 DNS 投毒时 `github.com → 28.0.0.28`，SSH 连接也会被拒绝（`Connection closed by 28.0.0.28 port 22`）。HTTPS 同样失败（`gnutls_handshake() failed`）。

**此时 git push 无法通过任何协议完成。** SYNTHESIZER_BODY 的容错逻辑（"记录错误但继续下一步"）正好覆盖此场景。报告已 commit 到本地，Telegram 推送仍可执行，待网络恢复后手动 `git push` 即可。
