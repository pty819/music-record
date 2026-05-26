#!/usr/bin/env python3

"""
Batch-create kanban scraper tasks for music sites, 2 at a time, chained via parents.

Workspace: dir:/home/liyifan/music-record/2026/{MM}/{DATE}/ (date-named subdir)
Each scraper writes its own {site_id}_reviews.json — no collisions.
Aggregator reads all of them from the same directory.

Usage:
  python3 kanban-batch-scrape.py          # dry run
  python3 kanban-batch-scrape.py --confirm # create tasks
"""

import json, subprocess, sys, os
from datetime import date

SITES_FILE = "/home/liyifan/.minimax/music-sites/sites.json"
OUTPUT_DIR = "/home/liyifan/music-record/2026"
TODAY = date.today()
DATE = TODAY.strftime("%Y-%m-%d")
MONTH = TODAY.strftime("%m")
BATCH_SIZE = 2


def run(cmd):
    use_shell = isinstance(cmd, str)
    result = subprocess.run(cmd, shell=use_shell, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def hermes_create(title, body, assignee="scraper", parents=None, skills=None, workspace=None):
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
    output = run(cmd)
    try:
        result = json.loads(output)
        return result.get("id") or result.get("task_id")
    except:
        print(f"Warning: could not parse JSON from: {output[:300]}", file=sys.stderr)
        return None


def cleanup_old_tasks():
    """Archive existing music-pipeline kanban tasks (scrape:* and aggregate:*).
    Uses `hermes kanban` CLI exclusively — never opens kanban.db directly
    to avoid WAL conflicts with the kanban dispatcher.
    Does NOT touch tasks from other domains."""
    import subprocess
    result = subprocess.run(
        ["hermes", "kanban", "list"],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return 0
    output = result.stdout.strip()
    if not output or output == "(no matching tasks)":
        return 0
    tasks = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        tid, status = parts[0], parts[1]
        title = parts[2] if len(parts) > 2 else ""
        if not tid.startswith("t_"):
            continue
        if status in ("done", "archived"):
            continue
        if title.startswith("scrape:") or title.startswith("aggregate:"):
            tasks.append((tid, status, title))
    if not tasks:
        return 0
    print(f"  [cleanup] archiving {len(tasks)} old music-pipeline tasks...")
    for tid, status, title in tasks:
        code = subprocess.run(
            ["hermes", "kanban", "archive", tid],
            capture_output=True, text=True, timeout=15
        )
        if code.returncode == 0:
            print(f"    archived {status:<8} {title[:50]}  ({tid[:12]}...)")
        else:
            print(f"    FAILED archive {tid}: {code.stderr.strip()}", file=sys.stderr)
    return len(tasks)


def main():
    confirm = "--confirm" in sys.argv
    with open(SITES_FILE) as f:
        d = json.load(f)
    sites = [
        s for s in d["sites"]
        if s.get("crawl_strategy") != "skip" and not s.get("skipped") and not s.get("has_rss")
    ]
    print(f"Active sites: {len(sites)}")
    for s in sites:
        print(f"  {s['name']}")
    print()
    if not confirm:
        print("Dry run. Pass --confirm to create tasks.")
        sys.exit(0)

    # ── Cleanup old music tasks before creating new ones ──
    archived = cleanup_old_tasks()
    if archived > 0:
        print(f"  Cleaned up {archived} stale music tasks")

    worker_skills = ["kanban-worker"]
    date_dir = f"{OUTPUT_DIR}/{MONTH}/{DATE}"
    ws = f"dir:{date_dir}"
    os.makedirs(date_dir, exist_ok=True)

    all_task_ids = []

    for site in sites:
        sid = site.get("id", site["name"].lower().replace(" ", "_"))
        name = site["name"]
        url = site.get("url") or site.get("reviews_url") or site.get("homepage", "")
        strategy = site.get("crawl_strategy", "playwright_headless")
        tags = ", ".join(site.get("tags", []))
        out_file = f"{date_dir}/{sid}_reviews.json"
        title = f"scrape: {name}"
        body = f"""**{name}** · {url} · {strategy} · {tags}

🔒 约束
━━━━━━━━━━━━━━━━
- 时间范围：只抓 3 天内文章，超期停止
- RSS 优先：有 RSS 就走 feedparser，不开浏览器
- Cookie 墙：navigate 后点击 Accept/Agree
- 非音乐过滤：跳过 (BLU-RAY)/(UHD)/(VOD)/(DVD)
- 特稿/访谈 → type: feature, score: null
- 空结果 → 输出 []，不报错不重试
- Paywall/CF → status: paywalled/blocked，返回 []

❌ 禁止
━━━━━━━━━━━━━━━━
- 禁止写 Python 脚本测日期逻辑（模板里的 cutoff 是正确的）
- 禁止 RSS 有数据还开浏览器交叉验证
- 禁止翻超过前 2 页列表页
- 日志超过 100 行说明你在过度分析，超过 300 行说明你有问题

✅ 步骤
━━━━━━━━━━━━━━━━
1. 检查 RSS → curl + feedparser，过滤 3 天条目
   - CDATA 全文用 summary 字段获取，strip HTML 取前 500 字
   - curl 超时（SSL 握手失败）→ 走 Camoufox 浏览器
2. 无 RSS → Camoufox 浏览器访问列表页，只翻前 2 页
3. Cookie 墙 → 检查并点击 Accept/Agree，等 1 秒
4. 提取：album, artist, score, url, source, pub_date, excerpt, type
5. 超 3 天停止翻页
6. 非音乐过滤：跳过含 (BLU-RAY)/(UHD)/(VOD)/(DVD) 条目
7. kanban_complete

📦 输出格式
━━━━━━━━━━━━━━━━
写入 {out_file}，JSON 格式：
{{
  "meta": {{"total": N, "scraped_at": "...", "cutoff_date": "~3天前"}},
  "items": [
    {{ "album", "artist", "score", "url", "source", "pub_date", "tags", "excerpt", "body", "site_id", "crawl_status", "type" }}
  ]
}}
type: "review" | "feature" | "tracklist"
❗ 必须包含 body 字段（全文正文，不截断）
❗ 必须使用 {{meta, items}} 外包装，不是裸数组
kanban_complete(summary="scraped N items from {name}", metadata={{"site": "{sid}", "count": N, "days_scanned": "3"}})"""

        tid = hermes_create(
            title=title,
            body=body,
            assignee="scraper",
            parents=None,
            skills=worker_skills,
            workspace=ws,
        )
        if tid:
            all_task_ids.append(tid)
            print(f"  {tid}: {name}")
        else:
            print(f"  FAILED: {name}", file=sys.stderr)

    # ── Final aggregator ────────────────────────────────────────────────
    agg_body = """✅ 步骤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 运行聚合脚本（全量去重 → 评分 → MiniMax 中文总结 → recommend markdown）

```bash
python3 /home/liyifan/music-record/bin/aggregate_reviews.py \\
  --date-dir %s \\
  --date %s
```

2. 同步 skill + 脚本（git 源 → ~/.local/bin/）

```bash
cp /home/liyifan/music-record/bin/kanban-batch-scrape.py /home/liyifan/.local/bin/
cp /home/liyifan/music-record/bin/fast-rss-scrape.py /home/liyifan/.local/bin/
cp /home/liyifan/music-record/bin/aggregate_reviews.py /home/liyifan/.local/bin/ 2>/dev/null || true
```

3. kanban_complete

```python
kanban_complete(
    summary="aggregated %d unique reviews, %d passed filter, recommend written to recommend/",
    metadata={"total": %d, "passed": %d}
)
```

4. Telegram 推送

读取 /home/liyifan/music-record/recommend/%s.md
用 send_message 推送到 Telegram Home 频道：
- ≤4000 字符 → 直接发送全部内容
- >4000 字符 → 发精简版（标题 + ★8+ + 统计 + "完整版见 GitHub 链接"）
"""

    from datetime import datetime
    date_obj = datetime.fromisoformat(DATE)
    git_month = date_obj.strftime("%m")
    N = len(all_task_ids)
    passed_placeholder = 0
    task_ids_file = f"/tmp/aggregator_parent_ids_{DATE}.json"
    with open(task_ids_file, 'w') as f:
        json.dump(all_task_ids, f)
    agg_body = agg_body % (
        date_dir, DATE,
        len(all_task_ids), passed_placeholder,
        len(all_task_ids), passed_placeholder,
        DATE
    )

    agg_id = hermes_create(
        title="aggregate: all music reviews",
        body=agg_body,
        assignee="scraper",
        parents=all_task_ids,
        skills=worker_skills,
        workspace=ws,
    )
    print(f"\n  Aggregator: {agg_id}")
    print(f"\nTotal: {len(all_task_ids)} scraper tasks + 1 aggregator")
    print(f"Concurrency: {BATCH_SIZE} at a time (parent-gated)")
    print(f"Workspace: {ws}")
    print(f"Output base: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()