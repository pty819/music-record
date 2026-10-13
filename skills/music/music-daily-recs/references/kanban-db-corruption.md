# Kanban DB Corruption — Failure Mode & Workaround

## 现象

`hermes kanban` CLI 所有命令静默失败或报错：
```
Error: file is not a database
sqlite3.DatabaseError: file is not a database
```

`~/.hermes/kanban.db` 文件存在且有大小（~5MB），但 `sqlite3` 模块无法打开，`file` 命令识别为 "data" 而非 SQLite。

## 根因

Gateway 在执行 `PRAGMA journal_mode=WAL` 时数据库文件损坏。可能发生在：
- Gateway crash后数据库文件未正常关闭
- WAL 模式切换时主机电源中断
- 数据库文件被部分写入后中断

## 诊断

```bash
# 1. 检查文件类型
file ~/.hermes/kanban.db
# 正常输出：SQLite 3.x...; 损坏输出：data

# 2. 测试 sqlite3 访问
python3 -c "import sqlite3; conn=sqlite3.connect('/home/liyifan/.hermes/kanban.db'); print(conn.execute('SELECT count(*) FROM tasks').fetchone())"
# 正常：返回数字; 损坏：sqlite3.DatabaseError: file is not a database

# 3. 检查 gateway 日志中的错误
grep "PRAGMA journal_mode=WAL" ~/.hermes/logs/gateway.log
# 损坏时会出现 sqlite3.DatabaseError

# 4. 检查 dispatcher tick 失败
grep "dispatcher.*tick failed" ~/.hermes/logs/gateway.log
```

## 影响

- `hermes kanban list` → 报错或空输出
- `hermes kanban create` → 任务创建失败（cron无法创建scraper任务）
- `hermes kanban archive` → 无法归档任务
- Gateway dispatcher 无法执行任务（但已启动的任务可能继续运行）

## 临时绕过：session_search 查找历史 task ID

即使 kanban CLI 损坏，**session 数据库**（`~/.hermes/sessions/sessions.db`）仍然可用。通过 `session_search` 可以找到历史 task ID，用于追踪已运行任务的状态。

```python
# 示例：从 session 历史中找到 scraper 任务 ID
session_search(query="scrape: boomkat", limit=3)
# 返回历史 session 记录，包含 task_id 和执行结果
```

## 根本修复

重建 kanban 数据库（当前 cron session 仍在运行因 dispatcher 使用内存中状态继续处理已启动的任务）：

```bash
# 1. 停止 gateway
systemctl --user stop hermes-gateway.service

# 2. 备份损坏文件
cp ~/.hermes/kanban.db ~/.hermes/kanban.db.corrupt.$(date +%Y%m%d%H%M%S)

# 3. 重建（从 gateway 自动创建新文件）
systemctl --user start hermes-gateway.service

# 4. 等待新文件创建
sleep 5 && ls -la ~/.hermes/kanban.db

# 5. 验证
python3 -c "import sqlite3; conn=sqlite3.connect('/home/liyifan/.hermes/kanban.db'); print(conn.execute('SELECT count(*) FROM tasks').fetchone())"
```

## 与 cron 任务的关系

- **cron 任务仍可运行**：已启动的 cron agent 在 session 层面执行，不依赖 kanban CLI
- **scraper 任务无法创建**：batch 脚本依赖 `hermes kanban create`
- **已启动的 scraper 任务可能继续**：如果 dispatcher 已将任务分发给 worker，worker 使用内存状态独立运行
- **当前 session 发现**：05-20 cron session 运行了 80+ 分钟到达 API call #89，但无 scraper JSON 文件输出，说明 scraper 任务从未成功创建（batch 脚本在 aggregator 创建阶段失败）

## 预防

- 避免在 Gateway 运行时直接修改 `kanban.db`
- 服务器重启前确保 Gateway 正常 shutdown（`systemctl stop`）
- 定期检查 `file ~/.hermes/kanban.db` 确认仍为 SQLite 格式
