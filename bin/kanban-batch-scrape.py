#!/usr/bin/env python3

"""

Batch-create kanban scraper tasks for music sites, 2 at a time, chained via parents.



Workspace: dir:/home/liyifan/music-record/2026/{MM}/{DATE}/ (date-named subdir)

Each scraper writes its own {{site_id}}_reviews.json — no collisions.

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

    Does NOT touch tasks from other domains. Runs directly on kanban DB

    to avoid CLI text-parsing fragility."""

    import sqlite3

    db_path = os.path.expanduser("~/.hermes/kanban.db")

    if not os.path.exists(db_path):

        print("  [cleanup] no kanban.db, skip", file=sys.stderr)

        return 0

    conn = sqlite3.connect(db_path)

    cur = conn.execute(

        "SELECT id, title, status FROM tasks "

        "WHERE (title LIKE 'scrape:%' OR title LIKE 'aggregate:%') "

        "AND status NOT IN ('archived', 'done')"

    )

    tasks = cur.fetchall()

    conn.close()

    if not tasks:

        print("  [cleanup] no music tasks to archive")

        return 0

    print(f"  [cleanup] archiving {len(tasks)} old music-pipeline tasks...")

    for tid, title, status in tasks:

        code = run(["hermes", "kanban", "archive", tid])

        print(f"    archived {status:<8} {title[:50]}  ({tid[:12]}...)")

    return len(tasks)



def main():

    confirm = "--confirm" in sys.argv

    with open(SITES_FILE) as f:

        d = json.load(f)

    sites = [

        s for s in d["sites"]

        if s.get("crawl_strategy") != "skip" and not s.get("skipped")

    ]

    print(f"Active sites: {len(sites)}")

    batches = []

    for i in range(0, len(sites), BATCH_SIZE):

        batches.append(sites[i:i+BATCH_SIZE])

    print(f"Batches: {len(batches)} (batch_size={BATCH_SIZE})")

    for i, b in enumerate(batches):

        print(f"  Batch {i+1}: {[s['name'] for s in b]}")

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

    prev_task_ids = []

    all_task_ids = []

    for batch_idx, batch in enumerate(batches):

        batch_num = batch_idx + 1

        parents = list(prev_task_ids)

        task_ids = []

        for site in batch:

            sid = site.get("id", site["name"].lower().replace(" ", "_"))

            name = site["name"]

            url = site.get("url") or site.get("reviews_url") or site.get("homepage", "")

            strategy = site.get("crawl_strategy", "playwright_headless")

            tags = ", ".join(site.get("tags", []))

            out_file = f"{date_dir}/{sid}_reviews.json"

            title = f"scrape: {name}"

            body = f"""抓取站点：{name}

URL：{url}

策略：{strategy}

标签：{tags}



⚠️ 重要约束 — 时间范围：只抓取**最近 3 天内**发布的文章。3 天之前的全部跳过。



任务：



1. 判断站点是否有 RSS：优先用 curl + feedparser 解析 RSS，过滤出最近 3 天条目



   🔸 许多站的 RSS 在 <description> CDATA 字段有完整正文（如 The Wire）。用 feedparser 的 summary 字段获取全文，strip HTML 后取前 500 字填入 excerpt。如果没有正文仅摘要则用摘要。



2. 如果没有 RSS：用 browser_navigate headless（通过 Camoufox 反检测引擎自动路由，非 vanilla Playwright）访问 reviews_url，只浏览列表页前 2 页，筛选 3 天内的文章



3. **Cookie 墙处理**（所有站点必须执行）：



   - browser_navigate 之后，检查页面是否有 cookie consent banner

   - 查找方式：找包含 "cookie" 的文本 + "agree" / "accept" / "I agree" 的按钮或链接

   - 如果找到任意 "Agree" / "Accept" / "I agree" 按钮，立即点击，等 1 秒让 banner 消失

   - 然后再继续提取内容



4. 对每篇评论抓取：专辑名、艺人、评分、评论URL、发布日期、来源、摘要



   ⚠️ 如果文章不是传统乐评格式（特稿/专题/访谈/音频节目）：将文章标题填入 album，栏目名或分类填入 artist，type 设为 "feature"，score 设为 null



5. **时间判断**：pub_date 在 3 天内则抓取；超过 3 天则停止，不再继续翻页

6. 如果该站**没有任何 3 天内的文章**：输出空数组 `[]`，不要报错，不要重试，直接结束

7. 遇到 paywall/cloudflare：标记 `"status": "paywalled"` 或 `"status": "blocked"`，返回空数组

8. **非音乐过滤**：提取标题后，如果 artist 或 album 包含 (BLU-RAY、 (BLU RAY、 (UHD、 (VOD)、 (DVD 等关键词，说明这是电影/碟片评测，不是音乐，跳过该条目

9. 输出：JSON 数组，写入 {out_file}

   每条格式：{{"album", "artist", "score", "url", "source", "pub_date", "tags", "excerpt", "site_id", "crawl_status", "type"}}

   type 取值："review"（传统乐评）或 "feature"（特稿/专题/访谈/音频节目）

10. kanban_complete(summary="scraped N items from {name}", metadata={{"site": "{sid}", "count": N, "days_scanned": "3"}})"""

            tid = hermes_create(

                title=title,

                body=body,

                assignee="scraper",

                parents=parents if parents else None,

                skills=worker_skills,

                workspace=ws,

            )

            task_ids.append(tid)

            print(f"  [{batch_num}] {tid}: {name} -> {sid}_reviews.json")

        prev_task_ids = list(task_ids)

        all_task_ids.extend(task_ids)

        print(f"Batch {batch_num} done (parents={len(parents)}, this batch={len(task_ids)})")

    # ── Final aggregator ────────────────────────────────────────────────

    # Use % formatting to avoid nested curly braces syntax error

    agg_body = """聚合步骤：

1. 运行聚合脚本：

```bash

python3 /home/liyifan/music-record/bin/aggregate_reviews.py \

  --date-dir %s \

  --date %s

```

2. 同步 skill + 脚本到 music-record：

```bash

cp ~/.hermes/skills/music/music-daily-recs/SKILL.md /home/liyifan/music-record/skills/music/music-daily-recs/

cp ~/.local/bin/kanban-batch-scrape.py /home/liyifan/music-record/bin/

cp /home/liyifan/music-record/bin/aggregate_reviews.py /home/liyifan/music-record/bin/aggregate_reviews.py

```

3. GitHub 推送（结果 + skill + 脚本一起）：

```bash

cd /home/liyifan/music-record

git add 2026/%s/%s/ recommend/%s.md

git add skills/music/music-daily-recs/SKILL.md bin/kanban-batch-scrape.py bin/aggregate_reviews.py

git commit -m "Daily: %s — %d reviews, %d passed filter"

git push

```

4. kanban_complete(summary="aggregated %d unique reviews, %d passed filter, recommend written to recommend/", metadata={"total": %d, "passed": %d})

"""

    from datetime import datetime

    date_obj = datetime.fromisoformat(DATE)

    git_month = date_obj.strftime("%Y-%m")

    N = len(all_task_ids)

    passed_placeholder = 0

    task_ids_file = f"/tmp/aggregator_parent_ids_{DATE}.json"

    with open(task_ids_file, 'w') as f:

        json.dump(all_task_ids, f)

    agg_body = agg_body % (

        date_dir, DATE,

        git_month, DATE, DATE,

        DATE,

        len(all_task_ids), passed_placeholder,

        len(all_task_ids), passed_placeholder,

        len(all_task_ids), passed_placeholder

    )

    agg_body = agg_body.replace(

        "all_task_ids = [%s]",

        f"# Load parent IDs from temp file to avoid shell length limit\nwith open('{task_ids_file}', 'r') as f:\n    all_task_ids = json.load(f)"

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