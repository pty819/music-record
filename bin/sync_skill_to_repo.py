#!/usr/bin/env python3
"""检测安装版 skill 与仓库版漂移，有差异就同步并提交推送。
被 cronjob 调用：安装版 skill 是实际被加载的那份，改了它仓库要跟上。
"""
import filecmp, os, shutil, subprocess, sys, json

REPO = "/home/liyifan/music-record"
SKILL_REPO = f"{REPO}/skills/music/music-daily-recs"
SKILL_INST = "/root/.hermes/skills/music/music-daily-recs"
SKIP_NAMES = {".git", "__pycache__", "node_modules", ".pyc"}


def walk(root):
    out = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_NAMES]
        for f in fns:
            if f.endswith(".pyc") or f.startswith("."):
                continue
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root)] = p
    return out


def main():
    changed, added = [], []
    # 1) SKILL.md + references: 安装版 -> 仓库（安装版是母版）
    for rel in ["SKILL.md"]:
        i, r = f"{SKILL_INST}/{rel}", f"{SKILL_REPO}/{rel}"
        if os.path.exists(i) and (not os.path.exists(r) or
                                  not filecmp.cmp(i, r, shallow=False)):
            shutil.copy2(i, r)
            changed.append(rel)

    inst_refs = os.path.join(SKILL_INST, "references")
    repo_refs = os.path.join(SKILL_REPO, "references")
    if os.path.isdir(inst_refs):
        os.makedirs(repo_refs, exist_ok=True)
        for f in sorted(os.listdir(inst_refs)):
            if not f.endswith(".md"):
                continue
            i, r = os.path.join(inst_refs, f), os.path.join(repo_refs, f)
            if not os.path.exists(r):
                shutil.copy2(i, r); added.append(f"references/{f}")
            elif not filecmp.cmp(i, r, shallow=False):
                shutil.copy2(i, r); changed.append(f"references/{f}")

    # 2) scripts: 安装版 -> 仓库 bin/（仓库 bin/ 是运行本体）
    inst_scripts = os.path.join(SKILL_INST, "scripts")
    repo_bin = os.path.join(REPO, "bin")
    if os.path.isdir(inst_scripts):
        for f in sorted(os.listdir(inst_scripts)):
            if not f.endswith(".py"):
                continue
            i, r = os.path.join(inst_scripts, f), os.path.join(repo_bin, f)
            if not os.path.exists(r):
                shutil.copy2(i, r); added.append(f"bin/{f}")
            elif not filecmp.cmp(i, r, shallow=False):
                shutil.copy2(i, r); changed.append(f"bin/{f}")

    if not changed and not added:
        print("NO_CHANGE")
        return 0

    print(f"DRIFT: changed={len(changed)} added={len(added)}")
    for c in changed[:20]:
        print(f"  ~ {c}")
    for a in added[:20]:
        print(f"  + {a}")

    # 3) 提交推送
    subprocess.run(["git", "-C", REPO, "add", "-A",
                    "skills/music/music-daily-recs", "bin"], check=True)
    if subprocess.run(["git", "-C", REPO, "diff", "--cached", "--quiet"],
                      capture_output=True).returncode == 0:
        print("NOTHING_STAGED")
        return 0

    msg = ("chore(skill): 自动同步本地 skill 改动到仓库\n\n"
           f"changed={len(changed)} added={len(added)}\n"
           + "\n".join(f"- {c}" for c in changed[:20])
           + "\n".join(f"- new {a}" for a in added[:20]))
    subprocess.run(["git", "-C", REPO, "commit", "-q", "-F", "-"],
                   input=msg, text=True, check=True)
    push = subprocess.run(["git", "-C", REPO, "push", "origin", "main"],
                          capture_output=True, text=True)
    print("PUSH_OK" if push.returncode == 0 else f"PUSH_FAIL: {push.stderr[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
