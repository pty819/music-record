# `agg_body` 模板格式化陷阱 —— 2026-05-14 实测记录

## 背景

`kanban-batch-scrape.py` 中的 `agg_body` 字符串是聚合器任务模板。
它同时包含：
1. **外层文本**：markdown 说明 + bash/git 命令（用 `%s`/`%d` 占位符）
2. **内嵌 Python 代码**（在 ` ```python ` 代码围栏内）：聚合器 agent 执行的实际逻辑

这两层有不同的变量替换需求，是 bug 高发区。

## 2026-05-14 发现的 5 个 Bug

### Bug 1：`%s`/`%d` 计数不匹配

```
模板代称：13 %s + 7 %d = 20
传值数量：18
差异：2 个 %d 缺失（kanban_complete 行的最后 2 个 %d）
错误：TypeError: not enough arguments for format string
```

**根因**：`kanban_complete` 行有 4 个 `%d`（`%d unique reviews, %d passed filter, {"total": %d, "passed": %d}`），但格式元组只传了 2 个。

**修复**：补齐元组，用 `re.findall(r'(?<!%)%[sd]', agg_body)` 手动统计并匹配。

### Bug 2：内嵌代码的 `{DATE}`/`{date_dir}` 不是 `%` 占位符

```python
# Before (broken)
DATE = "{DATE}"        # 字面量："{DATE}" ❌
date_dir = "{date_dir}" # 字面量："{date_dir}" ❌

# After (fixed)  
DATE = "%s"            # → "2026-05-14" ✅
date_dir = "%s"        # → "/home/liyifan/music-record/2026/05/2026-05-14" ✅
```

**根因**：用 `%` 格式化后，`%` 只替换 `%s`/`%d`，不替换 `{var}`。但内嵌代码仍保留了 f-string 时代的 `{var}` 占位符写法。

**后果**：聚合器 agent 执行时 `date_dir` 为字面字符串 → `os.listdir("{date_dir}")` → `FileNotFoundError`。`md_path` 输出到 `recommend/{DATE}.md`（文件名带花括号）。

### Bug 3：`MONTH` 变量遮蔽

```python
# 模块级 (line 21)
MONTH = TODAY.strftime("%m")   # "05"

def main():
    # line 84: 使用 MONTH
    date_dir = f".../{MONTH}/..."  # ERROR: MONTH 被视为局部变量
    
    # line 416: 重新赋值，Python 视为局部
    MONTH = date_obj.strftime("%Y-%m")  # "2026-05"
```

**根因**：Python 编译时看到 `main()` 内有 `MONTH = ...`，把整个函数的 `MONTH` 都视为局部。L84 读取时 L416 还没执行。

**修复**：改名 `git_month`，避免遮蔽。

### Bug 4：`passed` 变量作用域泄露

```python
# main() 中：
agg_body = agg_body % (
    ...
    len(passed),  # ERROR: passed 只在 agg_body 字符串中定义，不在 main() 作用域中
)
```

**根因**：模板字符串中的 Python 变量和 `main()` 函数的变量是不同命名空间。`passed` 在聚合器模板内定义（过滤 >=6分），但 `%` 格式化时在 `main()` 中引用。

**修复**：用 `passed_placeholder = 0` 代替，聚合器运行时自己计算。

### Bug 5：函数签名不匹配

```python
# 定义
def gen_cn_fallback(r):           # 1 个 dict 参数
    tags_raw = r.get("tags","")   # 从 dict 取标签

# 调用
gen_cn_fallback(excerpt, artist_album)  # 2 个字符串参数 ❌
```

**根因**：函数最初设计接收 review dict，调用改为传字符串后忘记同步更新定义。

**后果**：`TypeError` + `tags_raw` 永远为 `""` → 关键词匹配全部失效 → 中文总结退化为"值得关注的前卫实验声响"。

**修复**：改为 `def gen_cn_fallback_v1(excerpt_text, artist_album_str, tags_raw_str="")`，接收 3 个字符串参数。

## 正确验证流程

每次修改 `agg_body` 后：

```bash
# 1. 语法检查
python3 -m py_compile kanban-batch-scrape.py

# 2. 统计 %s/%d 数量
python3 -c "
import re
with open('kanban-batch-scrape.py') as f:
    text = f.read()
lines = text.split('\n')
agg = '\n'.join(lines[145:412])
s = len(re.findall(r'(?<!%)%s', agg))
d = len(re.findall(r'(?<!%)%d', agg))
print(f'{s} %s + {d} %d = {s+d}')
"

# 3. 模拟 % 格式化（Python 脚本中提取 agg_body 并格式化）
python3 -c "
with open('kanban-batch-scrape.py') as f:
    exec(compile(f.read(), 'kanban-batch-scrape.py', 'exec'))
# 或用 ast.parse 检查
"

# 4. Dry run
python3 kanban-batch-scrape.py

# 5. 如果你敢：--confirm 测试
# python3 kanban-batch-scrape.py --confirm
5. 函数签名变化后必须同步更新所有调用点

### Bug 6：`{{DATE}}`/`{{date_dir}}` f-string 双花括号错用（2026-05-19 发现 ✅ 已修复 2026-05-19）

**代码行**（agg_body 内嵌 Python 代码）：
```python
md_path = f"/home/liyifan/music-record/recommend/{{DATE}}.md"    # ❌
with open(f"{{date_dir}}/filtered.json", "w") as f:               # ❌
```

**根因**：Python f-string 中 `{{` 是字面大括号转义（产生 `{`），不是变量插值。所以 `{{DATE}}` 产生字面字符串 `{DATE}`，而不是变量 DATE 的值。

**验证**：
```python
DATE = "2026-05-19"
f"...{{DATE}}.md"   →  "/home/.../recommend/{DATE}.md"      ❌ 字面 {DATE}
f"...{DATE}.md"     →  "/home/.../recommend/2026-05-19.md"  ✅
```

**这是怎么进来的**：这段 agg_body 代码原本是给 LLM agent 看的指令，agent 不需要字面执行 Python。但后续演进中代码越来越可执行，双花括号却没人修。目前处于潜伏状态（因为 Bug 1 shell 反引号问题导致 aggregator 创建已失败，没走到执行这步）。

**修复**：改回单花括号：
```python
md_path = f"/home/liyifan/music-record/recommend/{DATE}.md"
with open(f"{date_dir}/filtered.json", "w") as f:
with open(f"{date_dir}/aggregated.json", "w") as f:
```

> ⚠️ 注意和 Bug 2 的区别：Bug 2 是 f-string 时代遗留下来的 `{var}` 占位符（不在 `%` 替换范围内），导致字面量 `{DATE}`。Bug 6 是 f-string 的双花括号转义问题，`{{DATE}}` 在 Python f-string 解析时也会变成字面 `{DATE}`，但原因不同——是转义过度。

### Bug 7（致命）：`hermes_create()` shell 反引号命令替换——aggregator 无法创建（2026-05-19 发现 ✅ 已修复 2026-05-19）

**症状**：`kanban-batch-scrape.py --confirm` 创建完 42 个 scraper task 后，在创建 aggregator task 时崩溃：
```
Syntax error: EOF in backquote substitution
```
aggregator 缺失，pipeline 断裂，必须走 fallback。

**代码路径**：
```python
# hermes_create() 第 85-97 行
cmd = (
    f"hermes kanban create {json.dumps(title)} "
    f"--body {json.dumps(body)} "
    f"--assignee {assignee}"
    f"{parent_args}{skill_args}{ws_arg}"
    f" --json"
)
output = run(cmd)  # run() → subprocess.run(cmd, shell=True)
```

**根因**：两层问题叠加：

1. `json.dumps(body)` 包裹双引号但**不转义反引号**（反引号不是 JSON 特殊字符）
2. `subprocess.run(cmd, shell=True)` 把命令传给 `/bin/sh -c`——在 shell 中，**双引号内的反引号仍然是命令替换**

agg_body 包含 ` ```python ` / ` ``` ` 代码围栏（约 6 个反引号），shell 误以为 ````python\nimport json...```` 是一个命令替换，尝试执行 `python\nimport json\n...` 作为 shell 命令。

**实际 shell 命令长什么样**：
```
hermes kanban create "aggregate: all music reviews" --body "```python\nimport json...```" ...
```

shell 把第一个反引号到最后反引号之间的所有内容当作命令替换执行 → 语法错误。

**修复（2026-05-19 实际应用——方案 B）**：

将 `hermes_create()` 改为构建 list 传参，不再拼接 shell 字符串。`run()` 函数自动检测入参类型：

```python
# run() — 检测入参类型，list → shell=False
def run(cmd):
    use_shell = isinstance(cmd, str)
    result = subprocess.run(cmd, shell=use_shell, capture_output=True, text=True)
    ...

# hermes_create() — 用 list 替代 f-string 拼接
def hermes_create(title, body, ...):
    cmd = ["hermes", "kanban", "create", title, "--body", body, "--assignee", assignee]
    if parents:
        for p in parents:
            cmd.extend(["--parent", p])
    if skills:
        for s in skills:
            cmd.extend(["--skill", s])
    if workspace:
        cmd.extend(["--workspace", workspace])
    cmd.append("--json")
    output = run(cmd)  # run() 检测到 list → shell=False，shell 完全不介入
```

**方案 B 的优势**：`subprocess.run(['hermes', ...], shell=False)` 完全绕过了 shell，body 中的任何特殊字符（反引号、`$`、`!`、`;`）都不会被解释为 shell 语法。同时避免了 `json.dumps()` 不转义反引号的问题——body 直接作为 argv 传递，不走 shell 解析。这是最彻底的修复。

**方案 C（不推荐）**：将 body 写入临时文件用 `--body-file` 传参——增加了文件 I/O 和清理负担，且 `hermes kanban create` 不一定支持 `--body-file`。

**关键原则**：当 agg_body 包含 shell 敏感字符（反引号、`$`、`!`）时，`json.dumps()` 不能提供 shell-safe 保护。必须额外处理。

## 关键原则

1. `%` 格式化只认识 `%s`/`%d`/`%r`，**不认识 `{var}`**
2. 内嵌代码中的占位符必须也是 `%s`/`%d`，不能用 `{var}` 假装会被替换
3. 函数内不要重新赋值与全局同名的变量
4. 模板变量和函数变量是分开的命名空间
5. 函数签名变化后必须同步更新所有调用点
