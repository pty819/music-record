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

⚠️ 重要：使用绝对路径，不要依赖 $HERMES_KANBAN_WORKSPACE。

输入目录：{date_dir}（绝对路径）
输入文件：{date_dir}/*_reviews.json（共 {len(all_task_ids)} 个）
输出文件（均使用绝对路径）：
  - {date_dir}/aggregated.json   （当天所有去重后的评论）
  - {date_dir}/filtered.json     （当天评分 >= 6 的评论）
  - /home/liyifan/music-record/recommend/{DATE}.md  （当天全量 markdown，直接作为唯一输出）

步骤：
1. cd {date_dir} && ls *_reviews.json 确认文件存在
2. 遍历 {date_dir}/*_reviews.json（绝对路径）
3. 解析所有 JSON 数组合并
4. 按 (album+artist) 去重，保留评分最高的来源
5. 按评分公司打分：total_score = critic_quality + taste_match + novelty + cross_domain_bonus + regional_bonus - mainstream_penalty
6. 输出 aggregated.json（全量） 和 filtered.json（>=6分）到 {date_dir}/
7. 生成全量 markdown（含 ★10/8/6 分级）→ 直接写入 /home/liyifan/music-record/recommend/{DATE}.md

   **Markdown 格式规范（必须遵守）：**
   ```
   # Daily Music Recommendations — {DATE}

   *Generated {TODAY.isoformat()} · N reviews from X sites · M passed filter (≥6/10)*

   ## ★10 — Top Picks

   **[Album] — [Artist]** [[score], source]
   [Listen/read →](url)
   > 完整推荐理由（从 excerpt 字段原样摘录，不要改写，不要用省略号截断）

   ## ★8 — Notable
   ...

   ## ★6 — Notable
   ...
   ```
   - 按评分分三栏：★10（>=9分）、★8（7-8分）、★6（6分）
   - 每条保留：专辑名、艺人、评分、来源URL、完整推荐理由
   - **推荐理由必须完整摘录自 JSON 的 excerpt 字段**，原文是什么就写什么，不要改写，不要截断，不要加省略号
   - 推荐理由要突出声音特征/创新点/场景感

8. **同步 skill + 脚本最新副本到 music-record**：
   ```bash
   mkdir -p /home/liyifan/music-record/skills/music/music-daily-recs
   mkdir -p /home/liyifan/music-record/bin
   cp /home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md /home/liyifan/music-record/skills/music/music-daily-recs/
   cp /home/liyifan/.local/bin/kanban-batch-scrape.py /home/liyifan/music-record/bin/
   ```
9. GitHub 推送（结果 + skill + 脚本一起）：
   ```bash
   cd /home/liyifan/music-record
   git add 2026/{MONTH}/{DATE}/ recommend/{DATE}.md
   git add skills/music/music-daily-recs/SKILL.md bin/kanban-batch-scrape.py data/sites.json
   git commit -m "Daily: {DATE} — N reviews, M passed filter"
   git push
   ```
10. kanban_complete(summary="aggregated N unique reviews, M passed filter, recommend written to recommend/", metadata={{"total": N, "passed": M}})"""

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
