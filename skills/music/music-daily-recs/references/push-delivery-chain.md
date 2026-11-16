# 推送链路的投递段（仅在用户主动问「消息怎么没收到」时查）

日常「推送呢」只验 GitHub push 链路（见 SKILL.md）。本文件记录投递段细节，供用户明确问起时使用。

## 投递段在哪

`~/.hermes/cron/deliveries.db` 的 `deliveries` 表（注意路径是 `cron/deliveries.db`；`~/.hermes/deliveries.db` 里没有表）。`for_failure=1` 的行是**失败通知本身**也没送出去。

```bash
python3 -c "
import sqlite3
c=sqlite3.connect('/root/.hermes/cron/deliveries.db'); c.row_factory=sqlite3.Row
rows=c.execute(\"SELECT status, created_at, error FROM deliveries ORDER BY created_at DESC LIMIT 20\").fetchall()
for r in rows: print(r['created_at'], r['status'], (r['error'] or '')[:120])
"
```

## 微信（iLink）平台前置条件

用户必须先给 bot 发过消息，bot 才能主动推送。长时间无人发言时投递段失败，error 形如：

```
live adapter send failed: iLink sendmessage session not ready: ret=-2 errcode=None errmsg=prepare failed — the user must send the bot a message first
```

适配器已经自动做过一次「去掉 context_token 重发」降级仍被拒 → **平台限制，不是 Hermes bug，没有任何配置能绕过**，只能等用户再次发言把窗口打开。

处置：告诉用户「你太久没给 bot 发消息了，微信侧不让我主动推」，**不要改适配器配置、不要刷重试**。

## 执行段与投递段的关系

执行成功（报告生成 + git push + cron status=completed）≠ 用户在微信上收到——投递是另一条通道（adapter → 平台 API）。但用户已明确不把投递当验收项；GitHub push 才是。

若用户主动要求排查投递，再查这段；否则不要主动提。
