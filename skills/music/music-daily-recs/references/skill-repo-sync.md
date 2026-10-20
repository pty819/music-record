# 安装版 skill ↔ GitHub 仓库：两棵树的职责与同步方向

## 两棵树，各自的母版不同

| 树 | 路径 | 母版 | 为什么 |
|---|---|---|---|
| 文档 | `~/.hermes/skills/music/music-daily-recs/` | **安装版** | 下一任 session 加载的是安装版；结论、方法论、references 都累积在那里 |
| 代码 | `/home/liyifan/music-record/bin/` | **仓库** | 生产 cron 的 prompt 是 `cd /home/liyifan/music-record`，跑的是仓库里的 `bin/` |

**方向搞反的代价是静默的**：文档同步反了 = 改动没被加载；代码同步反了 = 仓库里的改动被安装版覆盖回去。

## 为什么需要自动化

手工 `cp` 会漏。实测漂移规模：安装版 `SKILL.md` 累积到 37KB / 41 章节，仓库副本还停在
10.8KB / 13 章节——**仓库版从未收到过这些章节**，因为没有机制保证同步。安装版 `scripts/`
同样落后 4 个文件，其中 `prune_raw_data.py` 整个缺失。

所以同步必须是**定时、无人值守**的，而不是「记得就 cp」。

## 同步脚本

`bin/sync_skill_to_repo.py`（安装版在 `scripts/sync_skill_to_repo.py`）。

- **SKILL.md 正文**：安装版 → 仓库（安装版是母版）。
- **代码**：仓库 → 安装版。安装版独有的脚本补进仓库。
- **references**：**双向并集**。仓库独有的历史 reference 补回安装版（否则安装树断链），安装版独有的补进仓库；内容不同时以安装版为准。
- **无变化时 stdout 为空**（cron `no_agent` 模式下空输出不投递，不制造噪音）。
- 有变化时：git add → commit → push，然后打印 `SKILL_SYNCED: N changed -> pushed <hash>`。

cron 任务 `skill-sync-to-github`（job `d129e61e3cc1`，`every 120m`，`no_agent`，
`deliver: local`）。`no_agent` 模式只跑脚本、不起 LLM、不花 token。

### references 必须走并集：单向会造出断链

只做「安装版 → 仓库」时，仓库里独有的历史 reference 永远进不了安装树。而 `SKILL.md`
正文可能已经引用了它——实测就是 `SKILL.md` 引用 `2026-10-14-incremental-0700.md`，
该文件只在仓库树存在，安装树断链。**同步的是文件集合，不只是两边都有的那几个文件。**

### 逐字节一致 ≠ 引用完整

两棵树逐字节一致后，**仍要单独验引用完整性**：正文引用的每个 reference 在本树都得存在。
两边同步了同样的 23 个文件、正文也一致，但正文若引用了某个两边都没有的文件，断链照样存在。

## 传播延迟

wrapper（`~/.hermes/scripts/sync_skill_to_repo.sh`）执行的是**仓库副本** `bin/sync_skill_to_repo.py`。
所以改了安装版 `scripts/` 里的脚本，要到下一个 tick 才会进入仓库、并在再下一个 tick 生效。
改仓库里的脚本则下一个 tick 就同步到安装版。

## 验证同步真的工作

**别只跑脚本看它不报错。造一次真实漂移，走完整链路**：

1. 在安装版 `SKILL.md` 末尾追加一行标记
2. 跑同步脚本 → 应输出 `DRIFT:` 列出文件，然后 `SKILL_SYNCED: ... -> pushed <hash>`
3. **再跑一次 → 应无输出**（漂移已消除）
4. `git log --oneline -1` 确认新 commit 存在，且 `git rev-parse HEAD` == `origin/main`
5. 清掉测试标记，再跑一次同步让仓库回到干净状态

第 3 步才是判据：漂移从「被检出」变成「不存在」。只做第 2 步的话，脚本可能只报告了漂移而没消除它。

第 5 步之后**还要确认仓库里没有残留的测试标记**（`grep -c '标记名' SKILL.md` 应为 0），
否则测试产物会被当成真实内容 push 上去。

### 还要验引用完整性

逐字节一致之后，单独验一遍：正文引用的每个 reference / 脚本在本树都存在。
文件集合同步和链接完整性是两件事，前者成立不代表后者成立。

## 手工同步（脚本没跑时的兜底）

```bash
REPO=/home/liyifan/music-record
INST=/root/.hermes/skills/music/music-daily-recs
# 文档：安装版 → 仓库
cp $INST/SKILL.md $REPO/skills/music/music-daily-recs/SKILL.md
cp $INST/references/*.md $REPO/skills/music/music-daily-recs/references/
# 代码：仓库 → 安装版
cp $REPO/bin/*.py $INST/scripts/
```

比对（SKILL.md 和每个脚本都要比，只比文档会漏代码）：

```bash
diff $REPO/skills/music/music-daily-recs/SKILL.md $INST/SKILL.md | head -40
for f in $REPO/bin/*.py; do
  b=$(basename "$f")
  diff -q "$f" "$INST/scripts/$b" >/dev/null 2>&1 || echo "不一致: $b"
done
```

## 改代码时先想清楚改哪棵树

- 改**代码**（`bin/*.py`）：改仓库那份，然后等 tick 同步到安装版。**别只改装版**——
  下个 tick 会被仓库版本覆盖回去。
- 改**文档**（`SKILL.md`、`references/`）：改装版那份，等 tick 推到仓库。**别只改仓库**——
  下一任 session 加载的是安装版，改动不会被看到。

### ⚠️ 改错树 = 静默丢失，不会报错

同步脚本按母版方向单向覆盖。**你改在非母版那棵树上的内容，会被下一个 tick
静默抹掉**——脚本正常跑、正常报 `SKILL_SYNCED`、git commit 也成功，只是你写
的那段内容消失了。

实测踩过：在**仓库**树的 `SKILL.md` 里新增了一节「仓库里放什么、不放什么」，
下一个 tick 同步脚本按「安装版 → 仓库」的方向把安装版那份盖回去，那节内容
在两棵树里都不存在了。而两边依然「逐字节一致」、引用完整性检查依然通过、
脚本依然报成功。**一致 ≠ 正确：它只证明两棵树相同，不证明相同的那份是对的。**

判据（按顺序）：

1. 动手前先确认母版是哪棵树（本例：文档母版 = 安装版，代码母版 = 仓库）。
2. 写进母版那棵树，然后**立刻**跑一次同步脚本，看它是否报 `SKILL_SYNCED`
   且内容出现在**另一**棵树里。
3. 同步后**回读**非母版那棵树，确认你写的内容在那里——不要只看脚本输出。

### 母版方向不是常量，参考文件是唯一的例外点

`SKILL.md` 正文单向（安装版 → 仓库），代码单向（仓库 → 安装版），
但 `references/*.md` 走**并集**——因为仓库可能存着安装版没有的历史 reference，
单向同步会造出断链。并集规则的实现是「缺了就补上，冲突时以安装版为准」，
所以**新建 reference 要放在安装版**（它会单向推进仓库），而**只存在于仓库的
历史 reference 会被补回安装版**。两边同时新建同名但内容不同的文件，安装版赢。

## 别把临时文件带进仓库

同步脚本会 `git add -A bin skills/...`，所以临时备份必须排除。仓库内用
`.git/info/exclude`（不进版本库但文件留在本地），不要用 `.gitignore`——后者会被提交、污染所有人的克隆。
