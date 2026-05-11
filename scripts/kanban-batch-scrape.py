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
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

def hermes_create(title, body, assignee="scraper", parents=None, skills=None, workspace=None):
    parent_args = ""
    if parents:
        for p in parents:
            parent_args += f" --parent {p}"
    skill_args = ""
    if skills:
        for s in skills:
            skill_args += f" --skill {s}"
    ws_arg = f" --workspace {workspace}" if workspace else ""

    cmd = (
        f"hermes kanban create {json.dumps(title)} "
        f"--body {json.dumps(body)} "
        f"--assignee {assignee}"
        f"{parent_args}{skill_args}{ws_arg}"
        f" --json"
    )
    output = run(cmd)
    try:
        result = json.loads(output)
        return result.get("id") or result.get("task_id")
    except:
        print(f"Warning: could not parse JSON from: {output[:300]}", file=sys.stderr)
        return None

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

⚠️ 重要约束 — 时间范围：只抓取**最近 7 天内**发布的文章。7 天之前的全部跳过。

任务：
1. 判断站点是否有 RSS：优先用 curl + feedparser 解析 RSS，过滤出最近 7 天条目
2. 如果没有 RSS：用 browser_navigate headless 访问 reviews_url，只浏览列表页前 2 页，筛选 7 天内的文章
3. 对每篇评论抓取：专辑名、艺人、评分、评论URL、发布日期、来源、摘要
4. **时间判断**：pub_date 在 7 天内则抓取；超过 7 天则停止，不再继续翻页
5. 如果该站**没有任何 7 天内的文章**：输出空数组 `[]`，不要报错，不要重试，直接结束
6. 遇到 paywall/cloudflare：标记 `"status": "paywalled"` 或 `"status": "blocked"`，返回空数组
7. 输出：JSON 数组，写入 {out_file}
   每条格式：{{"album", "artist", "score", "url", "source", "pub_date", "tags", "excerpt", "site_id", "crawl_status"}}
8. kanban_complete(summary="scraped N reviews from {name} (last 7 days)", metadata={{"site": "{sid}", "count": N, "days_scanned": "7"}}"""

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
    agg_body = f"""读取所有 scraper 输出的 JSON 文件，合并去重，输出每日推荐。

输入目录：{OUTPUT_DIR}/{MONTH}/{DATE}
输入文件：*_reviews.json（共 {len(all_task_ids)} 个）
输出文件（三部分必须一起更新）：
  - {date_dir}/aggregated.json   （当天所有去重后的评论）
  - {date_dir}/filtered.json     （当天评分 >= 6 的评论）
  - {date_dir}/{DATE}.md         （当天全量 markdown，直接写入 music-record/2026/{MM}/{DATE}/DATE.md）
  - recommend/{DATE}.md           （top 20 精简版，直接写入 music-record/recommend/DATE.md）

步骤：
1. 遍历 $HERMES_KANBAN_WORKSPACE/*_reviews.json
2. 解析所有 JSON 数组合并
3. 按 (album+artist) 去重，保留评分最高的来源
4. 按评分公司打分：total_score = critic_quality + taste_match + novelty + cross_domain_bonus + regional_bonus - mainstream_penalty
5. 输出 aggregated.json（全量） 和 filtered.json（>=6分）
6. 生成全量 markdown：格式见 music-record 仓库规范 → 写入 {date_dir}/{DATE}.md
7. 生成 top 20 精简版 markdown（只含 >= 6 分中评分最高的前 20 条，每条只保留：日期、专辑、艺术家、评分、来源、一句话推荐理由）→ 写入 recommend/{DATE}.md
8. GitHub 推送（三部分一起 commit）：
   ```bash
   cd /home/liyifan/music-record
   git add 2026/{MONTH}/{DATE}/aggregated.json 2026/{MONTH}/{DATE}/filtered.json 2026/{MONTH}/{DATE}/{DATE}.md recommend/{DATE}.md
   git commit -m "auto: {DATE} daily recs"
   git push
   ```
9. kanban_complete(summary="aggregated N unique reviews, M passed filter, top 20 written to recommend/", metadata={{"total": N, "passed": M}})"""

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
