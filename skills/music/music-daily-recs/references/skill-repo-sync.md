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

- **文档**：安装版 → 仓库。仓库独有的历史 reference 补回安装版。
- **代码**：仓库 → 安装版。安装版独有的脚本补进仓库。
- 两边都只有一份、且内容不同时，按各自母版方向覆盖 → 收敛后两棵树逐字节一致。
- **无变化时 stdout 为空**（cron `no_agent` 模式下空输出不投递，不制造噪音）。
- 有变化时：git add → commit → push，然后打印 `SKILL_SYNCED: N changed -> pushed <hash>`。

cron 任务 `skill-sync-to-github`（job `d129e61e3cc1`，`every 120m`，`no_agent`，
`deliver: local`）。`no_agent` 模式只跑脚本、不起 LLM、不花 token。

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

## 别把临时文件带进仓库

同步脚本会 `git add -A bin skills/...`，所以临时备份必须排除。仓库内用
`.git/info/exclude`（不进版本库但文件留在本地），不要用 `.gitignore`——后者会被提交、污染所有人的克隆。
