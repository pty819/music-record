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

⚠️ 重要约束 — 时间范围：只抓取**最近 3 天内**发布的文章。3 天之前的全部跳过。

任务：
1. 判断站点是否有 RSS：优先用 curl + feedparser 解析 RSS，过滤出最近 3 天条目
2. 如果没有 RSS：用 browser_navigate headless 访问 reviews_url，只浏览列表页前 2 页，筛选 3 天内的文章
3. **Cookie 墙处理**（所有站点必须执行）：
   - browser_navigate 之后，检查页面是否有 cookie consent banner
   - 查找方式：找包含 "cookie" 的文本 + "agree" / "accept" / "I agree" 的按钮或链接
   - 如果找到任意 "Agree" / "Accept" / "I agree" 按钮，立即点击，等 1 秒让 banner 消失
   - 然后再继续提取内容
4. 对每篇评论抓取：专辑名、艺人、评分、评论URL、发布日期、来源、摘要
5. **时间判断**：pub_date 在 3 天内则抓取；超过 3 天则停止，不再继续翻页
6. 如果该站**没有任何 3 天内的文章**：输出空数组 `[]`，不要报错，不要重试，直接结束
7. 遇到 paywall/cloudflare：标记 `"status": "paywalled"` 或 `"status": "blocked"`，返回空数组
8. 输出：JSON 数组，写入 {out_file}
   每条格式：{{"album", "artist", "score", "url", "source", "pub_date", "tags", "excerpt", "site_id", "crawl_status"}}
9. kanban_complete(summary="scraped N reviews from {name} (last 3 days)", metadata={{"site": "{sid}", "count": N, "days_scanned": "3"}}"""

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
  - {date_dir}/aggregated.json   （当天所有去重后的评论，纯列表格式）
  - {date_dir}/filtered.json     （当天评分 >= 6 的评论）
  - /home/liyifan/music-record/recommend/{DATE}.md  （当天全量 markdown，直接作为唯一输出）

步骤：
1. cd {date_dir} && ls *_reviews.json 确认文件存在
2. 遍历 {date_dir}/*_reviews.json（绝对路径）
3. 解析所有 JSON 数组合并
4. 按 (album+artist) 去重，保留评分最高的来源
5. 执行评分代码（见下方），输出 total_score
6. 输出 aggregated.json（全量，纯列表）和 filtered.json（>=6分）到 {date_dir}/
7. 生成全量 markdown（含 ★10/8/6 分级）→ 直接写入 /home/liyifan/music-record/recommend/{DATE}.md

=== 可执行代码（必须执行）===
```python
import json, os
from datetime import datetime

DATE = "{DATE}"
date_dir = "{date_dir}"
TODAY = datetime.now()

# ── 读取所有 scraper JSON ──────────────────────────────────────
all_files = [f for f in os.listdir(date_dir) if f.endswith("_reviews.json")]
reviews = []
for fname in all_files:
    fpath = os.path.join(date_dir, fname)
    with open(fpath) as f:
        reviews.extend(json.load(f))
print(f"Loaded {{len(reviews)}} reviews from {{len(all_files)}} files")

# ── 去重：按 (album+artist) 保留评分最高的来源 ─────────────────
seen = {{}}
for r in reviews:
    key = (r.get("album",""), r.get("artist",""))
    old = seen.get(key, {{}})
    if "score" not in old or (r.get("score") and r.get("score",0) > old.get("score",0)):
        seen[key] = r
reviews = list(seen.values())
print(f"Deduplicated: {{len(reviews)}} unique")

# ── 评分函数（与 skill/SKILL.md 一致）────────────────────────────
def score_review(r):
    excerpt = r.get("excerpt","") or ""
    tags_raw = r.get("tags","")
    tags = [t.lower().strip() for t in tags_raw.split(",")] if isinstance(tags_raw,str) else tags_raw
    elen = len(excerpt)
    cq = min(5, elen // 100) if elen > 0 else 0
    avant_kw = ["experimental","avant-garde","free jazz","electroacoustic","drone",
                "ambient","idm","glitch","industrial","sound art","modern composition",
                "field recording","improvisation","noise","ritual","dark ambient",
                "dungeon synth","darksynth","synthwave"]
    tm = min(5, sum(1 for t in tags for k in avant_kw if k in t))
    novelty_kw = ["unique","rare","first","unusual","innovative","cross-cultural","world","ritual"]
    nov = min(3, sum(1 for kw in novelty_kw if kw.lower() in excerpt.lower()))
    domains = set()
    for t in tags:
        if any(k in t for k in ["jazz","improvisation"]): domains.add("jazz")
        if any(k in t for k in ["electronic","idm","glitch","ambient","drone"]): domains.add("electronic")
        if any(k in t for k in ["world","african","asian","latin","folk"]): domains.add("world")
        if any(k in t for k in ["classical","chamber","minimalist"]): domains.add("classical")
    cdb = max(0, len(domains) - 1) if len(domains) > 1 else 0
    reg_kw = ["southeast asia","south america","africa","middle east","central asia","southeast asian"]
    reg = 2 if any(kw in " ".join(tags) for kw in reg_kw) else (1 if any(kw in excerpt.lower() for kw in ["asia","africa","latin"]) else 0)
    
    # mainstream_penalty: 纯流行/无实验主流惩罚
    penalty_kw = ["pop","mainstream indie","indie pop","top 40","billboard"]
    mp = 0
    el_lower = excerpt.lower()
    if all(k in el_lower for k in ["pop","mainstream"]):
        mp = 3
    elif "pop" in el_lower and "experimental" not in el_lower and "avant" not in el_lower:
        mp = 2
    elif "mainstream" in el_lower and "experimental" not in el_lower:
        mp = 2 if "indie" in el_lower else 1
    
    # Synthwave / Retrowave / Dungeon Synth / Dark Ambient 额外降权
    # 只有 aesthetic 没有实质创新 → 降权
    dr = 0
    if "synthwave" in tags_str or "retrowave" in tags_str:
        # 检查是否只有怀旧 aesthetic 没有创新描述
        has_novelty = any(k in el_lower for k in ["innovative","modern","experimental","composition","texture","design"])
        if not has_novelty:
            if all(k in el_lower for k in ["retro","nostalgic"]):
                dr += 1
            if "vibes" in el_lower and "sound" not in el_lower and "textur" not in el_lower:
                dr += 1
    if ("dungeon synth" in tags_str or "dark ambient" in tags_str):
        # 检查是否只有低保真堆叠没有叙事/细节
        has_detail = any(k in el_lower for k in ["texture","layer","narrative","worldbuilding","composition","ritual"])
        if not has_detail and ("lo-fi" in el_lower or "noise" in el_lower):
            dr += 1
    
    pen = 1 if cq <= 1 else 0
    return max(0, cq + tm + nov + cdb + reg - mp - dr - pen)

# ── 执行评分 ───────────────────────────────────────────────────
for r in reviews:
    r["total_score"] = score_review(r)

scored = sorted(reviews, key=lambda x: x["total_score"], reverse=True)
passed = [r for r in scored if r["total_score"] >= 6]
print(f"Passed (>=6): {{len(passed)}}")

# ── 中文推荐理由生成函数 ───────────────────────────────────────
def gen_cn(r):
    excerpt = r.get("excerpt","") or ""
    tags_raw = r.get("tags","")
    tags_str = tags_raw.lower() if isinstance(tags_raw,str) else " ".join(tags_raw).lower()
    parts = []
    el = excerpt.lower()
    if "field recording" in tags_str: parts.append("实地录音素材构建声音地景")
    if any(k in tags_str for k in ["drone","ambient"]): parts.append("低频嗡鸣与氛围纹理")
    if any(k in tags_str for k in ["idm","glitch","electronic"]): parts.append("IDM/glitch 结构与电子音色设计")
    if any(k in tags_str for k in ["experimental","avant-garde"]): parts.append("前卫实验与解构手法")
    if any(k in tags_str for k in ["jazz","improvisation"]): parts.append("即兴爵士语汇")
    if any(k in tags_str for k in ["noise","industrial"]): parts.append("噪音/工业粗粝质感")
    if any(k in tags_str for k in ["classical","minimalist","chamber"]): parts.append("古典极简主义与室内乐语")
    if any(k in tags_str for k in ["world","african","asian","latin"]): parts.append("世界音乐元素")
    if any(k in tags_str for k in ["dark ambient","dungeon synth","darksynth"]): parts.append("暗黑氛围与仪式性声响")
    if "ritual" in el: parts.append("仪式性的声音进程")
    if "layer" in el or "texture" in el: parts.append("多层纹理堆叠")
    if "dark" in el or "horror" in el: parts.append("暗黑声景与心理张力")
    if "improvis" in el: parts.append("即兴演奏的现场能量")
    if "ukraine" in el or "war" in el: parts.append("战争创伤与声音记忆")
    if "korean" in el: parts.append("韩国传统音乐与当代电子的解构重构")
    if "geography" in el or "geological" in el: parts.append("地理/地景声景与文化根系")
    if "synthwave" in tags_str or "retrowave" in tags_str: parts.append("合成器复古美学")
    if "dungeon synth" in tags_str: parts.append("地下迷宫氛围与幻想叙事")
    if not parts: parts = ["值得关注的前卫实验声响"]
    return "；".join(parts[:4])

# ── 生成 markdown ─────────────────────────────────────────────
lines = [
    f"# Daily Music Recommendations — {DATE}\n",
    f"*Generated {{TODAY.isoformat()}} · {{len(reviews)}} reviews · {{len(passed)}} passed filter (≥6/10)*\n"
]
top = [r for r in scored if r["total_score"] >= 11]
mid = [r for r in scored if 8 <= r["total_score"] <= 10]
low = [r for r in scored if 6 <= r["total_score"] < 8]
if top:
    lines.append("## ★10 — Top Picks\n")
    for r in top:
        lines.append(f"**{{r['album']}} — {{r['artist']}}** [★{{r['total_score']}}], {{r.get('source','unknown')}}")
        lines.append(f"[阅读原文 →]({{r.get('url','#')}})")
        lines.append(f"> 🔶 *{{gen_cn(r)}}*\n")
        lines.append(f"> {{r.get('excerpt','')}}")
        lines.append("")
if mid:
    lines.append("## ★8-9 — Notable\n")
    for r in mid:
        lines.append(f"**{{r['album']}} — {{r['artist']}}** [★{{r['total_score']}}], {{r.get('source','unknown')}}")
        lines.append(f"[阅读原文 →]({{r.get('url','#')}})")
        lines.append(f"> 🔶 *{{gen_cn(r)}}*\n")
        lines.append(f"> {{r.get('excerpt','')}}")
        lines.append("")
if low:
    lines.append("## ★6-8 — 此外值得关注\n")
    for r in low:
        lines.append(f"**{{r['album']}} — {{r['artist']}}** [★{{r['total_score']}}], {{r.get('source','unknown')}}")
        lines.append(f"[阅读原文 →]({{r.get('url','#')}})")
        lines.append(f"> 🔶 *{{gen_cn(r)}}*\n")
        lines.append(f"> {{r.get('excerpt','')}}")
        lines.append("")

# ── 写文件 ────────────────────────────────────────────────────
md_path = f"/home/liyifan/music-record/recommend/{{DATE}}.md"
with open(md_path, "w") as f:
    f.write("\n".join(lines))
print(f"Wrote {{md_path}}")

with open(f"{{date_dir}}/filtered.json", "w") as f:
    json.dump(passed, f, ensure_ascii=False, indent=2)

with open(f"{{date_dir}}/aggregated.json", "w") as f:
    json.dump(scored, f, ensure_ascii=False, indent=2)

print("Done")
```

8. **同步 skill + 脚本最新副本到 music-record**：
   ```bash
   mkdir -p /home/liyifan/music-record/skills/music/music-daily-recs
   mkdir -p /home/liyifan/music-record/bin
   cp /home/liyifan/.hermes/skills/music/music-daily-recs/SKILL.md /home/liyifan/music-record/skills/music/music-daily-recs/
   cp /home/liyifan/.local/bin/kanban-batch-scrape.py /home/liyifan/music-record/bin/
   ```
9. **GitHub 推送（结果 + skill + 脚本一起）**：
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