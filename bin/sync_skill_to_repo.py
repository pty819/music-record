#!/usr/bin/env python3
"""把安装版 skill 与 GitHub 仓库之间的差异自动同步、提交、推送。

两棵树的母版不同，优先级也不同：
  - 文档（SKILL.md、references/*.md）：安装版是母版。下一任 session 加载的是
    安装版，结论都累积在那里，所以安装版 -> 仓库。
  - 代码（bin/*.py）：仓库是母版。生产 cron 跑的是仓库里的 bin/，所以仓库 -> 安装版。
  两边各自独有的文件按母版方向补齐，收敛后两棵树逐字节一致。

方向搞反的代价是静默的：文档反了 = 改动没被加载；代码反了 = 仓库里的改动
被安装版覆盖回去。

无变化时 stdout 为空（cron no_agent 模式下空输出不投递）；有变化时提交并推送，
然后打印一行摘要。
"""
import filecmp
import os
import shutil
import subprocess
import sys

REPO = "/home/liyifan/music-record"
SKILL_REPO = f"{REPO}/skills/music/music-daily-recs"
SKILL_INST = "/root/.hermes/skills/music/music-daily-recs"
REPO_BIN = f"{REPO}/bin"
INST_SCRIPTS = f"{SKILL_INST}/scripts"


def py_files(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(f for f in os.listdir(directory)
                  if f.endswith(".py") and not f.startswith("."))


def md_files(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(f for f in os.listdir(directory)
                  if f.endswith(".md") and not f.startswith("."))


def same(a, b):
    return os.path.exists(a) and os.path.exists(b) and filecmp.cmp(a, b, shallow=False)


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def main():
    repo_changed = []   # 写进仓库的改动
    inst_changed = []   # 写进安装版的改动

    # ── 文档：安装版 -> 仓库 ──────────────────────────────────
    i, r = f"{SKILL_INST}/SKILL.md", f"{SKILL_REPO}/SKILL.md"
    if os.path.exists(i) and not same(i, r):
        copy(i, r)
        repo_changed.append("SKILL.md")

    inst_refs = f"{SKILL_INST}/references"
    repo_refs = f"{SKILL_REPO}/references"
    for f in md_files(inst_refs):
        if not same(f"{inst_refs}/{f}", f"{repo_refs}/{f}"):
            copy(f"{inst_refs}/{f}", f"{repo_refs}/{f}")
            repo_changed.append(f"references/{f}")
    # 仓库独有的历史 reference 补回安装版，让安装版也拿全
    for f in md_files(repo_refs):
        if not same(f"{repo_refs}/{f}", f"{inst_refs}/{f}"):
            copy(f"{repo_refs}/{f}", f"{inst_refs}/{f}")
            inst_changed.append(f"references/{f}")

    # ── 代码：仓库 -> 安装版 ──────────────────────────────────
    for f in py_files(REPO_BIN):
        if not same(f"{REPO_BIN}/{f}", f"{INST_SCRIPTS}/{f}"):
            copy(f"{REPO_BIN}/{f}", f"{INST_SCRIPTS}/{f}")
            inst_changed.append(f"scripts/{f}")
    # 安装版独有的脚本补进仓库
    for f in py_files(INST_SCRIPTS):
        if not os.path.exists(f"{REPO_BIN}/{f}"):
            copy(f"{INST_SCRIPTS}/{f}", f"{REPO_BIN}/{f}")
            repo_changed.append(f"bin/{f}")

    if not repo_changed and not inst_changed:
        return 0

    if repo_changed:
        subprocess.run(
            ["git", "-C", REPO, "add", "-A", "skills/music/music-daily-recs", "bin"],
            check=True,
        )
        if subprocess.run(["git", "-C", REPO, "diff", "--cached", "--quiet"],
                          capture_output=True).returncode == 0:
            print("SKILL_SYNCED: 差异已一致，无可提交内容")
            return 0
        msg = ("chore(skill): 自动同步安装版 skill 改动到仓库\n\n"
               + "\n".join(f"- {c}" for c in repo_changed))
        subprocess.run(["git", "-C", REPO, "commit", "-q", "-F", "-"],
                       input=msg, text=True, check=True)
        push = subprocess.run(["git", "-C", REPO, "push", "origin", "main"],
                              capture_output=True, text=True)
        if push.returncode != 0:
            print(f"PUSH_FAIL: {push.stderr[:300]}")
            return 1
        head = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        print(f"SKILL_SYNCED: {len(repo_changed)} changed -> pushed {head}")
    else:
        print(f"SKILL_SYNCED: {len(inst_changed)} 文件已从仓库同步到安装版")

    for c in repo_changed + inst_changed:
        print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
