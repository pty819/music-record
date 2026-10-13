# Rollback 完整性核对（2026-06-08 教训）

> 当用户说"回退到今早 04:08 04:00 状态"或类似指令时，`git reset --hard` **不够**——还需要做完整性核对。

## 1. `git reset --hard` 不删 untracked 文件

`git reset --hard <commit>` 只动：
- **tracked** 文件：恢复到 `<commit>` 的状态（**包括删除** `<commit>` 之后添加的 tracked 文件）
- **git index** 和 **HEAD** 指针
- **不会动 untracked 文件**

⚠️ 如果 `<commit>` 之前磁盘上有但**没 tracked** 的文件（比如手工 cp 进去的），它们**继续留在磁盘上**。用户说"回退到 X 之前状态"通常**隐含希望磁盘也回到 X 之前**——必须**先问**或**手动 rm**。

```bash
# 查看 untracked
git status --short  # 看到 ?? 前缀的就是 untracked

# 列出 X 之前磁盘上有但 git 没 tracked 的文件
git ls-files --others --exclude-standard
```

## 2. 远端 GitHub 上残留的我之前 push 上去的 commit

`git reset --hard` 只动**本地 HEAD**，**远端 origin/main 仍然指向最新 commit**。如果之前 `git push` 把"我搞砸"的 commit 推上去了，**远端还残留着**。

下次 `git pull` 会把它们拉回来——等于"回退"自动撤销。

**正确回退**（**先问用户**要不要 force push）：

```bash
# 1. 本地 reset
git reset --hard <good_commit>

# 2. 问用户：要不要 force push 远端？
#    选项 A: yes — `git push --force origin main` 远端也回退
#    选项 B: no  — 远端保留旧 commit，本地落后（`git status` 显示 "behind N commits"）
#    选项 C: revert — `git revert <bad_commit>..<good_commit>` 创建反向 commit（保留历史）

# 选项 A 示例
git push --force origin main
```

⚠️ **未问用户就 force push 是危险操作**——可能影响其他人的 fork/clone/拉取。

## 3. 字节级核对（不要只信 `git log`）

用户问"是不是和 GitHub 04-08 04:00 之前一样"——**`git log --oneline` 看时间戳不够**（commit message 可能一样但内容不同），必须**字节级**核对：

```bash
# 比较本地 working tree 和远端指定 commit 的文件 SHA
for f in skills/music/music-daily-recs/SKILL.md bin/kanban-swarm.py bin/kanban-batch-scrape.py bin/fast-rss-scrape.py; do
    local_sha=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1 | cut -c1-12)
    remote_sha=$(git ls-tree <commit> "$f" | awk '{print $3}' | xargs -I {} git cat-file -p {} | sha256sum | cut -d' ' -f1 | cut -c1-12)
    if [ "$local_sha" = "$remote_sha" ]; then
        echo "  ✅  $f  $local_sha"
    else
        echo "  ❌  $f  local=$local_sha  remote=$remote_sha"
    fi
done

# 对比 deployed 路径（~/.local/bin/ ~/.hermes/skills/）
for f in /home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md /home/liyifan/.local/bin/kanban-swarm.py; do
    sha256sum "$f" | cut -d' ' -f1 | cut -c1-12 | xargs -I {} echo "  {}  $f"
done
```

**对照表应该全部 ✅**。任何 ❌ = 有文件没同步（常见原因：cp 没执行、shell expand 失败、文件在别的 path）。

## 4. untracked 也要检查

如果磁盘上某个文件**在 `<commit>` 之前不存在**（看 git history），但**现在存在**——它就是 untracked 残留。处理：

```bash
# 找出 04-08 04:00 之前磁盘上有但 git 没 tracked 的文件
# 用 stat mtime + git log 反查
for f in $(git ls-files --others --exclude-standard); do
    first_commit=$(git log --all --diff-filter=A --pretty=format:"%H" -- "$f" | head -1)
    if [ -z "$first_commit" ]; then
        echo "  $f: never tracked — 04-08 04:00 之前也不在 git"
    else
        first_date=$(git log -1 --pretty=format:"%ai" "$first_commit")
        echo "  $f: first tracked $first_date"
    fi
done
```

**判断**：如果某个文件**从未 tracked** 且 mtime 晚于目标 commit——它是**目标 commit 之后**加的（哪怕是别人加的），**用户说"回退"** = 也应该删。**但要先问**（可能是用户自己加的、不想丢）。

## 5. 完整回退 checklist（copy-paste 用）

```bash
# Step 1: 确认目标 commit
TARGET=$(git log --before="2026-06-08 04:00:00 +0800" --pretty=format:"%H" -1)
echo "Target: $TARGET"

# Step 2: 本地 reset
git reset --hard $TARGET

# Step 3: 列出 untracked
echo "=== Untracked files (may need manual rm) ==="
git status --short | grep "^??"

# Step 4: 字节级核对（哪些文件本地=远端 target）
echo "=== Byte-level SHA check vs $TARGET ==="
for f in $(git ls-tree -r --name-only $TARGET | head -20); do
    [ -f "$f" ] || continue
    local_sha=$(sha256sum "$f" | cut -d' ' -f1 | cut -c1-12)
    remote_sha=$(git ls-tree $TARGET "$f" | awk '{print $3}' | xargs -I {} git cat-file -p {} | sha256sum | cut -d' ' -f1 | cut -c1-12)
    [ "$local_sha" = "$remote_sha" ] && echo "  ✅  $f" || echo "  ❌  $f  $local_sha != $remote_sha"
done

# Step 5: 同步 deployed 路径
cp /home/liyifan/music-record/skills/music/music-daily-recs/SKILL.md \
   /home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md
cp /home/liyifan/music-record/bin/*.py /home/liyifan/.local/bin/

# Step 6: 问用户：要不要 force push 远端？
```

## 6. 这次的具体情况（2026-06-08）

| 项 | 状态 |
|---|---|
| 本地 reset 到 `ef90da6` (6-07 cron 报告) | ✅ |
| `kanban-batch-scrape.py` 恢复 | ✅ |
| SKILL.md 恢复 | ✅ |
| deployed `~/.local/bin/` 同步 | ⚠️ 漏了 `kanban-batch-scrape.py`（后补 cp） |
| 6 个 untracked `.py` (`bandwagon_asia, boomkat_bodies, hear65, roots_world, sea_of_tranquility_v2, world_music_central`) | ⚠️ 没删——但 04-08 04:00 之前这些文件不在 git 里（应该也删，但没问） |
| 远端 6 个 commit (89b3da4 → 7662821) | ❌ 还在远端——**没问**用户要不要 force push |
| 2026/06/2026-06-08/ 目录（6-08 cron 报告产物） | ❌ 被 reset --hard 删了（`08bb483` 是 tracked 的，被 reset 干掉）|

**6 个 untracked 残留** + **远端未 force push** = 这次回退**不完整**。下次该问就问，别擅自决定。

## Related pitfalls

- §4 #8 in SKILL.md — 工作流陷阱
- `references/2026-06-08-skill-refactor-overanalysis.md` — 同类失败模式
