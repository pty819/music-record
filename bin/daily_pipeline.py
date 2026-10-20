#!/usr/bin/env python3
"""music-daily-recs 出货管道。无 LLM，无 Kanban AND 门。

04:00 cron (no_agent) 跑整条：
  RSS → HTML → merge → 评分 → 报告 → git push → 末尾 spawn 5 个 Camoufox worker

07:00 watchdog 复用本脚本：缺报告就出货；尾巴 JSON 后到了就再 merge 补 push。

出货不依赖任何 worker complete。Boomkat / JazzTokyo 失败不得挡住当天报告。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# MUSIC_RECORD_ROOT 仅供测试沙箱覆盖；生产默认不变。
ROOT = Path(os.environ.get("MUSIC_RECORD_ROOT", "/home/liyifan/music-record"))
BIN = ROOT / "bin"
LOCK_PATH = Path("/tmp/music-daily-recs.lock")
MIN_SCORE = 3
_HERMES_HOME = Path.home() / ".hermes" / "hermes-agent"
STUCK_STATUSES = ("blocked", "todo", "ready", "running", "review", "triage", "scheduled")


def _log(msg: str) -> None:
    print(msg, flush=True)


def run(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int | None = None,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    _log(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        timeout=timeout,
        check=check,
        text=True,
        capture_output=capture,
    )


def date_dir_for(d: date) -> Path:
    return ROOT / "2026" / d.strftime("%m") / d.isoformat()


def report_path_for(d: date) -> Path:
    return ROOT / "recommend" / d.strftime("%Y") / d.strftime("%m") / f"{d.isoformat()}.md"


def acquire_lock() -> int:
    fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        _log("另一条管道正在跑（flock），本进程退出 0，避免双开评分。")
        sys.exit(0)
    os.write(fd, f"{os.getpid()} {datetime.now().isoformat()}\n".encode())
    return fd


def git_pull() -> None:
    r = run(["git", "pull", "--ff-only", "origin", "main"], check=False, timeout=120)
    if r.returncode != 0:
        _log("git pull 失败，继续用磁盘上的代码出货。")


def scrape_rss(date_dir: Path, days: str) -> None:
    date_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            "python3",
            str(BIN / "fast-rss-scrape.py"),
            "--days",
            days,
            "-o",
            str(date_dir / "rss_merged.json"),
        ],
        timeout=3600,
    )


def scrape_html(date_dir: Path, days: str) -> None:
    date_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            "python3",
            str(BIN / "scrape_html_parallel.py"),
            "--out-dir",
            str(date_dir),
            "--days",
            days,
            "--timeout",
            "180",
        ],
        timeout=3600,
    )
    stray = ROOT / "html_reviews.json"
    dest = date_dir / "html_reviews.json"
    if stray.exists() and not dest.exists():
        stray.replace(dest)
        _log(f"已把 CWD html_reviews.json 挪到 {dest}")


def merge(date_dir: Path) -> int:
    r = run(
        [
            "python3",
            str(BIN / "merge_scraped.py"),
            "--date-dir",
            str(date_dir),
            "-o",
            "scraped_raw.json",
        ],
        check=False,
        timeout=120,
        capture=True,
    )
    if r.stderr:
        _log(r.stderr.rstrip())
    raw_path = date_dir / "scraped_raw.json"
    if r.returncode != 0 or not raw_path.exists():
        payload = {
            "meta": {
                "total": 0,
                "merged_from": {},
                "scraped_at": datetime.now().isoformat(),
                "empty": True,
            },
            "items": [],
        }
        raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        _log("merge 0 条，写了空 scraped_raw.json，继续出货。")
        return 0
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    return len(data.get("items") or [])


def write_empty_processed(date_dir: Path, reason: str) -> None:
    payload = {
        "meta": {
            "total": 0,
            "empty": True,
            "reason": reason,
            "processed_at": datetime.now().isoformat(),
        },
        "items": [],
    }
    (date_dir / "processed.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def write_report(d: date, date_dir: Path, items: list) -> Path:
    out = report_path_for(d)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not items:
        md = (
            f"# 🎵 每日音乐推荐 — {d.isoformat()}\n\n"
            "共整理 0 条乐评，筛选 0 条推荐。\n\n"
            f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
            "*数据来源：0 条乐评 → 推荐 0 条*\n"
        )
        out.write_text(md, encoding="utf-8")
        _log(f"空报告 → {out}")
        return out
    r = run(
        [
            "python3",
            str(BIN / "generate_report.py"),
            "--date-dir",
            str(date_dir),
            "-i",
            "processed.json",
            "--date",
            d.isoformat(),
            "--min-score",
            str(MIN_SCORE),
        ],
        timeout=60,
    )
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"generate_report.py 失败，报告不在 {out}")
    return out


def score(date_dir: Path) -> int:
    raw_path = date_dir / "scraped_raw.json"
    if not raw_path.exists():
        write_empty_processed(date_dir, "no scraped_raw.json")
        return 0
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    n = len(data.get("items") or [])
    if n == 0:
        write_empty_processed(date_dir, "scraped_raw empty")
        return 0
    r = run(
        [
            "python3",
            str(BIN / "process_reviews.py"),
            "--date-dir",
            str(date_dir),
            "-i",
            "scraped_raw.json",
            "-o",
            "processed.json",
            # 2026-10-18：GLM (z.ai Coding Plan) 兜底后降并发 3→2，避免触发 z.ai 限流
            "--max-workers",
            "2",
        ],
        check=False,
        timeout=7200,
    )
    proc_path = date_dir / "processed.json"
    if r.returncode != 0 or not proc_path.exists():
        raise SystemExit(f"process_reviews.py 失败 rc={r.returncode}")
    processed = json.loads(proc_path.read_text(encoding="utf-8"))
    items = processed.get("items") or []
    low = [i for i in items if i.get("total_score", 0) <= 2]
    if low:
        raise SystemExit(f"processed.json 仍有 {len(low)} 条 <=2 分，拒绝 push")
    return len(items)


def git_push_daily(d: date, date_dir: Path, msg: str | None = None) -> bool:
    report = report_path_for(d)
    # 只提交成品报告 + 归档增量。raw 中间产物（date_dir 下的 rss_merged/
    # scraped_raw/processed/*_reviews.json）是可再生的中间态：报告已完整覆盖
    # 其中每一条（报告 ### 条目数 == processed.json items 数，逐日核对过），
    # 留在仓库里只会让每天的 commit 膨胀几百 KB，且 raw 按策略只保留 3 天，
    # 跟踪它会让 .gitignore 与 retention 策略互相打架。
    paths = [
        str(report.relative_to(ROOT)),
        "data/fluid_radio_archive.json",
    ]
    run(["git", "add", "--"] + paths, check=False)
    # ⚠️ `git add` 撞上 .gitignore 时会打印 "ignored by one of your .gitignore
    # files" 并跳过该文件，但退出码仍是 0 —— commit 照样成功、push 照样成功，
    # 成品日报却根本没进仓库。实测 2026-10-20 踩中：.gitignore 里无锚定的
    # `2026/` 把 recommend/2026/ 一起排除了。
    # 所以 add 之后必须显式确认报告真的进了 index，否则直接失败。
    rel = str(report.relative_to(ROOT))
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0:
        raise SystemExit(
            f"❌ 报告 {rel} 没有进入 git index（多半被 .gitignore 挡住了）。\n"
            f"   成品日报没进仓库，push 成功也不算数。\n"
            f"   排查：git check-ignore -v {rel}\n"
            f"   若命中 .gitignore 里的目录规则，记得加前导斜杠锚定到仓库根"
            f"（如 `/2026/` 而不是 `2026/`），否则会连 recommend/ 下的成品一起排除。"
        )
    # 日更提交不带日志
    for extra in list(date_dir.glob("*_log.txt")) + list(date_dir.glob("*.log")):
        run(["git", "reset", "HEAD", "--", str(extra.relative_to(ROOT))], check=False)
    run(["git", "reset", "HEAD", "--", "logs/"], check=False)
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(ROOT),
        check=False,
    )
    if status.returncode == 0:
        _log("没有要提交的日更文件（可能已经 push 过）。")
        return False
    msg = msg or f"music-recs: {d.isoformat()} daily recommendations"
    r = run(["git", "commit", "-m", msg], check=False)
    if r.returncode != 0:
        _log("git commit 无变更或失败。")
        return False
    r = run(["git", "push", "origin", "main"], check=False, timeout=180)
    if r.returncode != 0:
        raise SystemExit("git push 失败，报告已在本地。看上面的实际错误，不要归因 GFW。")
    _log(f"已 push origin/main：{msg}")
    return True


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {"items": data}


def incremental_update(d: date, date_dir: Path, skip_push: bool = False) -> str:
    """07:00 增量：只给当天 processed.json 里没有的条目评分。

    - 身份键 = url_norm.item_key（规范化 URL）。
    - 已成功评分的条目（含 <=2 被删的、预过滤的）一律冻结，分数原样复用。
    - meta.score_error_keys 里的失败条目允许重试。
    - 没有新条目 → 不评分、不重写报告、不 commit、不 push。
    - 新条目全部评分失败 → 报告和 processed.json 原样保留，不 push。
    返回状态字符串，供日志 / 测试断言。
    """
    sys.path.insert(0, str(BIN))
    from url_norm import item_key  # noqa: E402

    proc_path = date_dir / "processed.json"
    raw_path = date_dir / "scraped_raw.json"
    old_proc = _load_json(proc_path)
    old_meta = old_proc.get("meta") or {}
    old_items = old_proc.get("items") or []
    old_raw_bytes = raw_path.read_bytes() if raw_path.exists() else None

    retry_keys = set(old_meta.get("score_error_keys") or [])
    if "scored_keys" in old_meta:
        known = set(old_meta["scored_keys"])
    else:
        # 旧版 processed.json（无 scored_keys）：保守地把 04:00 时 raw 里所有条目视为已评，
        # 低分/失败无法区分，故不重试，只补真正新到的条目。
        old_raw = json.loads(old_raw_bytes) if old_raw_bytes else {}
        known = {item_key(i) for i in (old_raw.get("items") or [])}
    known |= {item_key(i) for i in old_items}
    known -= retry_keys

    def restore_raw() -> None:
        if old_raw_bytes is not None:
            raw_path.write_bytes(old_raw_bytes)

    merge(date_dir)
    raw_items = (_load_json(raw_path).get("items") or [])
    seen: set[str] = set()
    new_items = []
    for it in raw_items:
        k = item_key(it)
        if k in known or k in seen:
            continue
        seen.add(k)
        new_items.append(it)

    if not new_items:
        restore_raw()
        _log(f"增量 {d.isoformat()}: 无新条目，不评分、不重写报告、不 push。")
        return "noop"

    _log(f"增量 {d.isoformat()}: {len(new_items)} 条新条目（含重试 {len(seen & retry_keys)}）待评分")
    inc_in = date_dir / "incremental_raw.json"
    inc_out = date_dir / "incremental_processed.json"
    inc_in.write_text(
        json.dumps({"meta": {"total": len(new_items), "incremental": True}, "items": new_items},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    inc_out.unlink(missing_ok=True)
    try:
        r = run(
            ["python3", str(BIN / "process_reviews.py"), "--date-dir", str(date_dir),
             "-i", inc_in.name, "-o", inc_out.name, "--max-workers", "1"],
            check=False, timeout=7200,
        )
        inc = _load_json(inc_out) if (r.returncode == 0 and inc_out.exists()) else {}
    finally:
        inc_in.unlink(missing_ok=True)
        inc_out.unlink(missing_ok=True)

    inc_meta = inc.get("meta") or {}
    new_scored = set(inc_meta.get("scored_keys") or [])
    if not new_scored:
        restore_raw()
        _log(f"增量 {d.isoformat()}: 新条目评分全部失败（rc={r.returncode}），保留现有报告，不 push。")
        return "all-failed"

    old_keys = {item_key(i) for i in old_items}
    new_kept = [i for i in (inc.get("items") or [])
                if i.get("total_score", 0) > 2 and item_key(i) not in old_keys]
    items = old_items + new_kept  # 旧条目原样在前，分数不变
    items.sort(key=lambda i: i.get("total_score", 0), reverse=True)  # 稳定排序

    meta = dict(old_meta)
    meta["scored_keys"] = sorted(known | new_scored)
    meta["score_error_keys"] = sorted(
        (retry_keys - new_scored) | set(inc_meta.get("score_error_keys") or [])
    )
    meta["total"] = int(old_meta.get("total") or 0) + len(new_items) - len(seen & retry_keys)
    meta.setdefault("incremental_runs", []).append({
        "at": datetime.now().isoformat(),
        "new": len(new_items),
        "scored": len(new_scored),
        "failed": len(inc_meta.get("score_error_keys") or []),
        "kept": len(new_kept),
    })
    proc_path.write_text(json.dumps({"meta": meta, "items": items}, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    write_report(d, date_dir, items)
    if not skip_push:
        git_push_daily(
            d, date_dir,
            msg=f"music-recs: {d.isoformat()} incremental +{len(new_kept)} (scored {len(new_scored)})",
        )
    _log(f"增量 {d.isoformat()}: scored={len(new_scored)} kept_new={len(new_kept)} total_kept={len(items)}")
    return "updated"


def spawn_swarm() -> None:
    r = run(["python3", str(BIN / "kanban-swarm.py"), "--confirm"], check=False, timeout=120)
    if r.returncode != 0:
        _log(f"kanban-swarm.py 失败 rc={r.returncode}。出货已完成，探索 worker 未创建。")


def sweep_music_kanban() -> dict[str, int]:
    """07:00：music tenant 卡死任务 complete + 全部未归档任务 archive。

    只动 tenant=music。出货不依赖看板，所以 running/blocked 到点一律收掉，
    避免第二天看板堆僵尸卡。complete 失败（例如 parent 未满足）就直接 archive。
    """
    counts = {"completed": 0, "archived": 0, "failed": 0}
    if str(_HERMES_HOME.resolve()) not in sys.path:
        sys.path.insert(0, str(_HERMES_HOME.resolve()))
    try:
        from hermes_cli import kanban_db as kb  # type: ignore
        from hermes_cli.kanban_db_connect import connect_closing  # type: ignore
    except ImportError as e:
        _log(f"sweep_music_kanban: 无法导入 kanban_db ({e})")
        return counts

    with connect_closing() as conn:
        open_tasks = list(kb.list_tasks(conn, tenant="music", include_archived=False))
        stuck = [t for t in open_tasks if t.status in STUCK_STATUSES]
        for t in stuck:
            ok = False
            try:
                ok = kb.complete_task(
                    conn,
                    t.id,
                    summary="watchdog sweep: stale music task closed",
                    metadata={"swept_by": "daily_watchdog", "prior_status": t.status},
                )
            except Exception:
                ok = False
            if ok:
                counts["completed"] += 1
            else:
                counts["failed"] += 1

        leftover = list(kb.list_tasks(conn, tenant="music", include_archived=False))
        for t in leftover:
            try:
                if kb.archive_task(conn, t.id):
                    counts["archived"] += 1
                else:
                    counts["failed"] += 1
            except Exception:
                counts["failed"] += 1
        # complete 可能把 parent-gated 子卡放成 ready，再扫一次免得 dispatcher 接走
        leftover = list(kb.list_tasks(conn, tenant="music", include_archived=False))
        for t in leftover:
            try:
                if kb.archive_task(conn, t.id):
                    counts["archived"] += 1
            except Exception:
                counts["failed"] += 1
    return counts


def report_on_origin(d: date) -> bool:
    rel = f"recommend/{d.strftime('%Y')}/{d.strftime('%m')}/{d.isoformat()}.md"
    r = subprocess.run(
        ["git", "cat-file", "-e", f"origin/main:{rel}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def newest_reviews_mtime(date_dir: Path) -> float:
    mtimes = []
    for p in date_dir.glob("*_reviews.json"):
        try:
            mtimes.append(p.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else 0.0


def processed_mtime(date_dir: Path) -> float:
    p = date_dir / "processed.json"
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="music-daily-recs 出货管道（无 LLM）")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--days", default="1.5")
    p.add_argument("--skip-scrape", action="store_true", help="跳过 RSS/HTML，用已有 JSON")
    p.add_argument("--skip-swarm", action="store_true", help="不创建 Camoufox worker")
    p.add_argument("--skip-score", action="store_true", help="跳过评分（已有 processed.json）")
    p.add_argument("--skip-push", action="store_true")
    p.add_argument(
        "--if-needed",
        action="store_true",
        help="watchdog：报告已在 origin/main 且无更新尾巴则静默退出",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    lock_fd = acquire_lock()
    try:
        os.chdir(ROOT)
        d = date.fromisoformat(args.date) if args.date else date.today()
        date_dir = date_dir_for(d)
        date_dir.mkdir(parents=True, exist_ok=True)

        ship = True
        incremental = False
        if args.if_needed:
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(ROOT),
                check=False,
                timeout=60,
                capture_output=True,
            )
            on_origin = report_on_origin(d)
            stale_tail = newest_reviews_mtime(date_dir) > processed_mtime(date_dir) + 1
            ship = (not on_origin) or stale_tail
            # 报告已在 origin 且有 processed.json → 只做增量，已推送分数冻结
            incremental = on_origin and (date_dir / "processed.json").exists()
            if ship:
                _log(
                    f"watchdog 补货 {d.isoformat()}: "
                    f"on_origin={on_origin} stale_tail={stale_tail}"
                )
                args.skip_scrape = (date_dir / "rss_merged.json").exists()
                args.skip_swarm = True

        if ship and incremental:
            git_pull()
            status = incremental_update(d, date_dir, skip_push=args.skip_push)
            _log(f"INCREMENTAL {d.isoformat()} status={status}")
        elif ship:
            git_pull()

            if not args.skip_scrape:
                scrape_rss(date_dir, args.days)
                scrape_html(date_dir, args.days)

            n_raw = merge(date_dir)
            _log(f"merge {n_raw} 条")

            if args.skip_score and (date_dir / "processed.json").exists():
                processed = json.loads((date_dir / "processed.json").read_text(encoding="utf-8"))
                items = processed.get("items") or []
                n_kept = len(items)
            else:
                n_kept = score(date_dir)
                processed = json.loads((date_dir / "processed.json").read_text(encoding="utf-8"))
                items = processed.get("items") or []

            write_report(d, date_dir, items)
            _log(f"保留 {n_kept} 条 >=3 分 → {report_path_for(d)}")

            pushed = False
            if not args.skip_push:
                pushed = git_push_daily(d, date_dir)

            if not args.skip_swarm:
                spawn_swarm()

            # 清理 3 天前的原始抓取数据，只留 recommend/ 报告。
            # 2026-10-18：原设计每天把 rss_merged/scraped_raw/processed 等 JSON
            # 全留在仓库里，4 月至今积到 316MB。报告已完整覆盖成品信息（抽查 39 天，
            # 报告 ### 条目数与 processed.json 逐日一致，零差异）。
            #
            # 测试沙箱必须跳过：沙箱里的日期目录（2026-10-14 等）是固定 fixture，
            # 在 3 天保留窗口外，prune 会把它们当成过期数据删掉，导致断言 FileNotFound。
            if os.environ.get("MUSIC_RECORD_ROOT"):
                _log("测试沙箱模式，跳过原始数据清理。")
            else:
                prune_rc = subprocess.run(
                    [sys.executable, str(BIN / "prune_raw_data.py"),
                     "--keep-days", "3", "--apply", "--commit"],
                    cwd=str(ROOT), check=False, timeout=600,
                ).returncode
                if prune_rc != 0:
                    _log(f"清理原始数据失败 rc={prune_rc}，不影响已 push 的报告。")

            _log(
                f"DONE {d.isoformat()} raw={n_raw} kept={n_kept} "
                f"pushed={pushed} report={report_path_for(d)}"
            )

        if args.if_needed:
            swept = sweep_music_kanban()
            if swept["completed"] or swept["archived"] or swept["failed"]:
                _log(
                    f"kanban sweep music: completed={swept['completed']} "
                    f"archived={swept['archived']} failed={swept['failed']}"
                )
            elif not ship:
                return 0  # 无补货、无僵尸卡：空 stdout，不投递
        return 0
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
