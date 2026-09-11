# 2026-06-09 cron session heredoc indentation failure

> 这是**工具级硬约束**导致的失败模式，与 `2026-06-08-skill-refactor-overanalysis.md`（LLM 虚构 bug 故事）**同构但根因不同**。两者预防手段也不同——本案例是 **wrapper 必须 pre-commit 到 repo**，上案例是 **重构 SKILL.md 时不要凭代码推测写"实测"**。

## 一句话根因

`SKILL.md` Step 3 内嵌了一段 **50 行的 heredoc Python wrapper**（并行起 12 个 scrape 进程）。2026-06-09 04:00 cron 触发，LLM session 试图在 `/tmp` 现场**重新生成**这份 wrapper——**6 种写法全部失败**：

1. heredoc with leading tabs/spaces → 所有前导空白被吃
2. `write_file` with explicit indentation → body 缩进被不一致地剥掉
3. `write_file` with `exec("""...""")` string body → 字符串字面量内同样剥掉
4. 通过 asm.py 拼装 (`parts.append("    SCRIPTS...`)) → 只 1 空格缩进存活，body `for`/`if` 同深度 = SyntaxError
5. `textwrap.dedent` → 移除了**所有**共同前导空白
6. `chr(32)` / `S*4` 生成缩进 → f-string 被搞乱（`chr(37)` + `"m"` 在 f-string 里 = unmatched paren）

session 最后抛 `RuntimeError` 退出，Step 3/4/5 全部未跑。**RSS 阶段 86 条抓到了但没合并，没派 9 Camoufox worker**。

## 工具级约束（不是 LLM 错）

hermes 的 `write_file` 和 `terminal` heredoc 在**多行 Python + 嵌套缩进**场景下，**leading whitespace 不可信**。这不是 LLM 写得不好——是工具链不保留嵌套缩进。

**可行的 workaround 顺序**（按可靠性从高到低）：

1. ✅ **`write_file` 一次性写完整文件**（无 heredoc，无 python -c）——**已验证可靠**
2. ⚠️ `terminal` heredoc 写 Python——**仅当代码无嵌套缩进**（单层 `if`/`for`）才安全
3. ❌ 在 session 内多次 `write_file` 拼装大文件——失败率高
4. ❌ 任何"先写框架再 sed 填内容"——失败率接近 100%

## 修复（已 commit `8c2a36f`）

把 50 行 heredoc wrapper 从 SKILL.md 抽出来 → `bin/scrape_html_parallel.py`（commit 进 git，**7.5KB**）。SKILL.md Step 3 塌缩为 4 行调用：

```bash
python3 /home/liyifan/.local/bin/scrape_html_parallel.py \
  --out-dir "$DATE_DIR" \
  --days 1.5 \
  --timeout 180
```

cron session 不再现场生成 Python——只 `cp` + `python3 ...`。

## 经验法则（适用于所有 cron skill）

> **任何 cron skill 需要的"中间 wrapper"（并行调度、文件 IO、HTTP 重试）都应该在仓库里**有 commit 版本**，不是 SKILL.md 里的 inline 代码块。

**判定标准**：
- 代码块 > 5 行？ → commit 到 `bin/`
- 代码块有嵌套 `for`/`if`/`try`？ → 强制 commit
- 代码块有 `def` 内部用 `def`（closure）？ → 强制 commit
- 单纯命令链（`cmd1 | cmd2 | cmd3`）？ → 留在 SKILL.md OK

## dry-run 验证（事实，不是推断）

```bash
TEST_DIR=/tmp/scrape_html_dryrun2_$$
HERMES_KANBAN_WORKSPACE=/tmp python3 ~/music-record/bin/scrape_html_parallel.py \
  --out-dir "$TEST_DIR" --days 1.5 --timeout 180
```

**结果**（180s 实测）：
- 12 个进程全部 launch 成功（pid 18186..18207）
- 11/12 写出有效 JSON（all_about_jazz=8, dark_entries_be=1, downbeat=0, free_jazz_blog=2, mixmag_asia=8, musique_machine=0, resident_advisor=0, sea_of_tranquility=3, songlines=40, squids_ear=0, wild_city=5）
- 1/12 (`jazz_trail`) 命中 180s timeout（rc=124, 0 字节）——**这是 scrape_jazz_trail.py 自己的早停缺失问题，不是 wrapper bug**（详见下）
- `scrape_sea_of_tranquility` 走 `out_dir` 模式（自写文件 + 独立 `.log`），不再污染 json

## 顺带发现（独立 bug，不在本次修复范围）

1. **`scrape_sea_of_tranquility.py` 接口不一致**——只它支持 `--out-dir` 自写文件，stdout 是日志。其余 11 个走 stdout。Wrapper 用 `mode` 字段分流。
2. **`scrape_jazz_trail.py` 主循环没早停**（不像 `scrape_sea_of_tranquility` 有 5 条连续 < cutoff 早停）。SKILL.md 旧描述 "翻页多但 --days 1.5 会正确过滤" **不准确**——1.5 天只过滤单页内 items，不停止翻页。Cloudflare 一慢就超 180s。修法：在 `main()` 翻页循环加 "连续 N 条日期 < cutoff 就 break"。

## 与 overanalysis 案例的对照

| 维度 | overanalysis（06-08） | heredoc failure（06-09） |
|------|---------------------|-------------------------|
| 触发 | SKILL.md 章节缺失 | SKILL.md 章节里嵌了 50 行 Python |
| 失败模式 | 读代码 → 编 bug 故事 → 写"实测" | 现场写代码 → 6 种写法全 SyntaxError |
| 根因 | LLM 推断 ≠ LLM 验证 | 工具链不保留嵌套缩进 |
| 修法 | §4 #8 工作流陷阱（验证纪律） | Wrapper pre-commit 到 `bin/`（工具纪律） |
| 类比 | 数据空 → 不接受 → 反复重抓 | 工具不支持 → 不接受 → 反复试错 |

**两个案例的共同点**：都是 agent **拒绝接受"做不到"**。overanalysis 拒绝接受"我看不懂 v5.1 代码"，heredoc failure 拒绝接受"我不能写嵌套缩进 Python"，都反复重试 → 越界。

**两个案例的不同点**：overanalysis 的越界是**知识性**（编 bug 故事），heredoc failure 的越界是**工具性**（绕过工具约束）。前者靠"先验证再写"，后者靠"接受工具能力边界，把 wrapper 提前 commit"。

## 后续行动项

- [x] 修 `scrape_jazz_trail.py` 主循环早停 → 详见 `references/scrape-jazz-trail-pagination-investigation.md`（已诊断完成，待用户确认 commit）
- [ ] 检查 `SKILL.md` 其他 step 是否有 heredoc Python（grep `cat > .* << 'PYEOF'`）—— Step 4/5 看着像纯 bash，应该没
- [x] 修 `references/scrape-script-cli-args.md` 矩阵：`scrape_sea_of_tranquility.py` 已**支持** `--out-dir`（2026-06-09 验证）——本轮已更新
