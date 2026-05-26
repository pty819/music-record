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

    # ── Create parent-gated aggregator task ─────────────────────────
    if all_task_ids:
        agg_title = f"aggregate: {DATE} music post-processing"
        agg_body = (
            "🔒 约束\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "- 严格按顺序执行 Step 1→2→3→4，一步不能少\n"
            "- 每一步检查 exit code，失败则重试一次\n"
            "- 只用 terminal 工具运行以下命令，不要多做事\n"
            "- 不要调用 kanban_create / delegate_task / web_search 等无关工具\n"
            "\n"
            "❌ 禁止\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "- 禁止推理、分析、解释、或自行假设数据\n"
            "- 禁止开浏览器或写临时脚本\n"
            "- 日志超 50 行说明你在过度分析\n"
            "\n"
            "✅ 步骤\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "Step 1: 合并所有抓取数据 → scraped_raw.json\n"
            "\n"
            "cd /home/liyifan/music-record\n"
            'DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"\n'
            "python3 /home/liyifan/.local/bin/merge_scraped.py \\\n"
            '  --date-dir "$(pwd)/$DATE_DIR" \\\n'
            "  -o scraped_raw.json\n"
            "\n"
            "验证: scraped_raw.json 存在且有 items 数组\n"
            "\n"
            "Step 2: 并发评分 + 中文总结 → processed.json\n"
            "\n"
            "cd /home/liyifan/music-record\n"
            'DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"\n'
            "python3 bin/process_reviews.py \\\n"
            '  --date-dir "$DATE_DIR" \\\n'
            "  -i scraped_raw.json \\\n"
            "  -o processed.json \\\n"
            "  --max-workers 3\n"
            "\n"
            "验证: processed.json 存在且含 total_score + _cn_summary\n"
            "如果 MiniMax rate limit (429)，重试一次；仍失败则跳过（保留可用数据）\n"
            "\n"
            "Step 3: 生成推荐 markdown\n"
            "\n"
            "cd /home/liyifan/music-record\n"
            'DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"\n'
            "python3 bin/generate_report.py \\\n"
            '  --date-dir "$DATE_DIR" \\\n'
            "  -i processed.json \\\n"
            '  --date "$(date +%Y-%m-%d)"\n'
            "\n"
            "验证: recommend/$(date +%Y-%m-%d).md 存在\n"
            "\n"
            "Step 4: 清理 .py 调试文件 + git push\n"
            "\n"
            "cd /home/liyifan/music-record\n"
            'DATE_DIR="2026/$(date +%m)/$(date +%Y-%m-%d)"\n'
            'rm -f "$DATE_DIR"/*.py\n'
            'git add -A "$DATE_DIR" "recommend/$(date +%Y-%m-%d).md" \\\n'
            "  bin/process_reviews.py bin/generate_report.py \\\n"
            "  bin/kanban-batch-scrape.py bin/merge_scraped.py\n"
            'git commit -m "music-recs: $(date +%Y-%m-%d) daily recommendations (kanban aggregator)" || true\n'
            "git push origin main 2>&1\n"
            "\n"
            "Step 5: 完成任务\n"
            "\n"
            'kanban_complete(summary="music-recs post-processing for $(date +%Y-%m-%d): merge -> score -> report -> git push")\n'
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "‼️ 仅执行以上步骤，不多做任何事。"
        )
        agg_tid = hermes_create(
            title=agg_title,
            body=agg_body,
            assignee="scraper",
            parents=all_task_ids,
            skills=worker_skills,
            workspace=ws,
        )
        if agg_tid:
            print()
            print(f"  ── Aggregator ────────────────────────────────")
            print(f"  ✅ Created aggregator: {agg_title}")
            print(f"     Aggregator ID: {agg_tid}")
            print(f"     Parents: {len(all_task_ids)} scraper tasks")
            print(f"     🕐  Will auto-dispatch when ALL scrapers complete")
            print(f"     📋  Pipeline: merge_scraped → process_reviews → generate_report → git push")
        else:
            print(f"  FAILED to create aggregator task", file=sys.stderr)

    print(f"\n✅ Created {len(all_task_ids)} Camoufox scraper tasks")
    print(f"   All tasks independent + 1 parent-gated aggregator")
    print(f"   Workspace: {ws}")
    print(f"   Cron session can now exit — kanban will finish the rest.")


if __name__ == "__main__":
    main()