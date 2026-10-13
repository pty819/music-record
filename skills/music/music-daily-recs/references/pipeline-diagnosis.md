# Pipeline Diagnosis — Stuck/Broken Pipeline Debugging

**核心原则**：怀疑 → 验证 → 再怀疑 → 再验证。不要靠分析猜测，先拿数据。

## 诊断步骤（按顺序）

### 0. 回溯历史 cron 运行（先看"发生了什么"再看"为什么"）

```bash
# 列出最近 cron 输出（每次运行一个 .md 文件）
ls -lt ~/.hermes/cron/output/ec5ea562d589/ | head -10

# 读某次运行的完整报告（含 prompt + agent 输出 + error）
cat ~/.hermes/cron/output/ec5ea562d589/YYYY-MM-DD_HH-MM-SS.md

# 快速找失败原因
grep -i 'error\|fail\|traceback\|RuntimeError\|blocked' \
  ~/.hermes/cron/output/ec5ea562d589/YYYY-MM-DD_HH-MM-SS.md
```

cron 输出文件命名格式：`YYYY-MM-DD_HH-MM-SS.md`（北京时间）。文件头部是 cron prompt（skill SKILL.md 全文 + 用户附加指令），接着是 agent 的执行报告。如果运行失败，尾部有 `## Error` 段。

### 1. 看 kanban board 状态

```bash
hermes kanban list | grep "scrape:\|Verify:\|Synthesize:"
```

关注三件事：
- **计数**：多少 `✓ done`、多少 `◻ todo`、多少 `running`
- **停滞**：`✓ done` 不再增长（plateau）但 `◻ todo` 还有 → dispatcher 卡死
- **孤儿**：旧任务卡在 `◻ todo` 指向已归档的 parent

### 2. 看 kanban DB 时间戳（比 list 快 10 倍）

```bash
python3 -c "
import sqlite3, datetime
db = sqlite3.connect('/home/liyifan/.hermes/kanban.db')
tz = datetime.timezone(datetime.timedelta(hours=8))
def bj(ts):
    if ts is None: return '--'
    return datetime.datetime.fromtimestamp(ts, tz=tz).strftime('%H:%M:%S')
cur = db.execute('SELECT id, title, status, started_at, completed_at FROM tasks WHERE created_at > strftime(\"%s\", \"now\", \"-1 day\") ORDER BY created_at')
for r in cur.fetchall():
    print(f'{bj(r[3]):>8}  {bj(r[4]):>8}  {r[2]:<8}  {r[1][:60]}')
db.close()
"
```

### 3. 看具体 worker/verifier/synthesizer 日志

```bash
ls -lt ~/.hermes/kanban/logs/ | head -10
# 找到卡住的 task_id
cat ~/.hermes/kanban/logs/<task_id>.log | grep -i "error\|fail\|exception"
```

日志行数显著偏多（>200 行）的 worker 是可疑对象。iter 烧到 90/90 失败 = 几乎肯定是"全空站反复验证"或"修 Python 缩进"问题。

### 4. 看实际文件

```bash
# 检查推荐文件
ls -la ~/music-record/recommend/$(date +%Y-%m-%d).md
file_size=$(stat -c%s ~/music-record/recommend/$(date +%Y-%m-%d).md)
# 如果 < 8KB → 大概率 LLM 评分全 fallback（关键词拼接）

# 检查抓取 JSON 是否就位
ls ~/music-record/2026/$(date +%m)/$(date +%Y-%m-%d)/*_reviews.json | wc -l
```

### 5. 查 cron job 状态

```bash
hermes cron list | grep music-daily-recs
```

关注 `last_status`、`last_delivery_error`。

⚠️ 命令是 `hermes cron list` 不是 `hermes cronjob list`（后者不存在）。

### 5b. 查看具体 kanban task 详情（blocked/failed 根因）

```bash
hermes kanban show <task_id>
```

输出含：status、assignee、workspace、Diagnostics（错误码）、Events（时间线）、Runs（每次执行的结果）。重点关注：
- `!! [error]` 行 → 具体失败原因（iteration budget exhausted / agent timeout / gave_up）
- `Events` 里 `timed_out` → `gave_up` 序列 → 说明重试也失败了

### 6. 看 git log 验证历史

```bash
cd ~/music-record
git log --oneline -- 'recommend/2026-*.md' | head -10
```

对比文件生成时间 vs 预期时间。如果每天 commit 时间都不同（有的凌晨、有的下午、有的第二天），说明 pipeline 一直不稳定，不是今天才开始。

## 常见误判

| 你以为 | 实际 | 证据 |
|--------|------|------|
| "某 worker 跑很久所以卡死" | 它只跑了 9 分钟，但等了 4 小时才轮到自己 | 看 DB time |
| "历史上都是五点多就完成了" | 只有第一天是，后面大多数下午/次日凌晨 | 看 git log 时间 |
| "pipeline 今天才出问题" | 每天都延迟，只是你没盯着看 | 10 天有 9 天延迟 |
| "sync 就好了" | 数据库已损坏，file= data 不是 SQLite | `file kanban.db` |
| "skill 改了就行" | cron job prompt 也要手动 update | `hermes cron list` 看 prompt_preview |
| "只有那一个 worker 没跑完，其他都好了" | **一个 blocked worker 阻塞整条 pipeline**（见下节） | `hermes kanban list` 看 verifier 是否 todo |

## 级联阻塞模式（Cascading Blocker）— 关键陷阱

**一个 blocked worker → 整天的推荐消失。** 这不是"那一个站点没抓到"的问题——是结构性的 pipeline 断裂。

Kanban Swarm 依赖链：`Root → [Workers] → Verifier → Synthesizer`
- Verifier 设置 `parent=所有 workers`，必须**全部 done** 才解锁
- Synthesizer 设置 `parent=verifier`，必须 verifier done 才解锁
- 任何一个 worker `blocked` → verifier 永远 todo → synthesizer 永远 todo → **无 recommend、无 Telegram、无 git push**

**实际案例**（2026-06-08）：
Sea of Tranquility 的 Camoufox worker 耗尽 90 次迭代预算 → retry 2 次也失败 → `blocked`。结果：RSS 73 条 + HTML 18 条 = 91 条数据已就位，但 verifier/synthesizer **永远没跑**，当天推荐完全丢失。

**诊断方法**：
```bash
hermes kanban list | grep -E "blocked|error"
# 如果有任何 blocked/error 的 scrape: 任务 → 该天 pipeline 断裂
```

**修复方法**（按优先级）：
1. `hermes kanban complete <blocked_task_id>` → 手动标记完成，解锁 verifier
2. 如果数据已缺失：手动跑 `process_reviews.py` + `generate_report.py` 用已抓数据出报告
3. 预防：确保所有 kanban worker 有合理的迭代预算；高风险站点用 HTML 脚本替代 Camoufox worker

## 修复后验证

每次修完，做三件事：
1. **证明修好了** — 重新跑一遍，看到真实数据出来
2. **同步到处** — 本地 skill + repo skill + `~/.local/bin/` 三者一致
3. **更新 cron prompt** — skill 如果有 Step 0 或执行步骤的改动，cron job 也要 update
