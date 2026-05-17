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
   🔸 许多站的 RSS 在 <description> CDATA 字段有完整正文（如 The Wire）。用 feedparser 的 summary 字段获取全文，strip HTML 后取前 500 字填入 excerpt。如果没有正文仅摘要则用摘要。
2. 如果没有 RSS：用 browser_navigate headless 访问 reviews_url，只浏览列表页前 2 页，筛选 3 天内的文章
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
    agg_body = """读取所有 scraper 输出的 JSON 文件，合并去重，输出每日推荐。

⚠️ 重要：使用绝对路径，不要依赖 $HERMES_KANBAN_WORKSPACE。

输入目录：%s（绝对路径）
输入文件：%s/*_reviews.json（共 %d 个）
输出文件（均使用绝对路径）：
  - %s/aggregated.json   （当天所有去重后的评论，纯列表格式）
  - %s/filtered.json     （当天评分 >= 6 的评论）
  - /home/liyifan/music-record/recommend/%s.md  （当天全量 markdown，直接作为唯一输出）

步骤：
1. cd %s && ls *_reviews.json 确认文件存在
2. 遍历 %s/*_reviews.json（绝对路径）
3. 解析所有 JSON 数组合并
4. 按 (album+artist) 去重，保留评分最高的来源
5. 执行评分代码（见下方），输出 total_score
6. 输出 aggregated.json（全量，纯列表）和 filtered.json（>=6分）到 %s/
7. 生成全量 markdown（含 ★10/8/6 分级）→ 直接写入 /home/liyifan/music-record/recommend/%s.md

=== 可执行代码（必须执行）===
```python
import json, os
from datetime import datetime

DATE = "%s"
date_dir = "%s"
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

# ── 评分函数 v2（内容驱动 + 站点基线）───────────────────────────
# Site-level taste baseline from sites.json tags
SITE_TAGS = {
    "musique_machine": ["dark ambient","industrial","electroacoustic","experimental","noise"],
    "squids_ear": ["experimental","electronic","sound art","avant-garde","improvisation"],
    "igloo_magazine": ["experimental electronic","idm","ambient","glitch","electroacoustic"],
    "hhv_mag": ["electronic","vinyl culture","electroacoustic","experimental"],
    "a_closer_listen": ["instrumental","experimental","ambient","drone","field recording"],
    "roots_world": ["world music","roots","folk","traditional"],
    "world_music_central": ["world music","traditional music","world fusion","experimental"],
    "free_jazz_blog": ["free jazz","avant-jazz","improvised music"],
    "the_quietus": ["experimental","electronic","jazz","world","avant-garde"],
    "jazz_trail": ["avant-garde jazz","experimental","improvisation"],
    "avant_music_news": ["experimental","weird","progressive","avant-garde"],
    "all_about_jazz": ["jazz","fusion","avant-garde","avant-jazz","world"],
    "the_wire": ["experimental","avant-garde","free jazz","electronic","drone","ambient","world","contemporary","improvisation"],
}

def get_site_taste_baseline(site_id):
    st = SITE_TAGS.get(site_id, [])
    st_str = " ".join(st)
    score = 0
    if any(k in st_str for k in ["experimental","avant-garde","free jazz","electroacoustic","drone","ambient","idm","glitch","industrial","noise","improvisation","sound art","field recording"]):
        score += 2
    if any(k in st_str for k in ["world","folk","electronic","minimalist","ritual","weird"]):
        score += 1
    return min(2, score)

def score_review(r, site_id="musique_machine"):
    excerpt = r.get("excerpt","") or r.get("summary","") or ""
    tags_raw = r.get("tags","") or r.get("genre","") or ""
    tags = [t.lower().strip() for t in tags_raw.split(",")] if isinstance(tags_raw,str) else (tags_raw or [])
    tags_str = tags_raw.lower() if isinstance(tags_raw,str) else " ".join(t.lower() for t in tags_raw).lower()
    el = excerpt.lower()
    elen = len(excerpt)
    
    # CQ: logarithmic, capped at 3 (reduced from 5)
    cq = min(3, elen // 150 + (1 if elen %% 150 > 75 else 0)) if elen > 0 else 0
    
    # TM: 3-layer - site baseline + entry tags + excerpt scan
    site_base = get_site_taste_baseline(site_id)
    avant_kw = ["experimental","avant-garde","free jazz","electroacoustic","drone","ambient","idm","glitch","industrial",
                "sound art","modern composition","field recording","improvisation","noise","ritual","dark ambient",
                "dungeon synth","darksynth","synthwave","world fusion","fusion"]
    entry_tag_match = min(3, sum(1 for t in tags for k in avant_kw if k in t))
    excerpt_match = 0
    if entry_tag_match < 2:
        excerpt_kw = ["experimental","avant-garde","free jazz","electroacoustic","drone","ambient","idm","glitch","industrial","noise","field recording","improvisation","fusion"]
        match_count = sum(1 for k in excerpt_kw if k in el)
        if match_count >= 2: excerpt_match = 1
    tm = min(5, site_base + entry_tag_match + excerpt_match)
    
    # NOV: expanded keyword list
    nov_kw = ["unique","rare","first","unusual","innovative","cross-cultural","world","ritual","exploration","boundary","genre-defying","groundbreaking","fusion","breakthrough","singular","unconventional","pushing"]
    nov = min(3, sum(1 for kw in nov_kw if kw in el))
    
    # CDB: scan excerpt too for domain keywords
    domains = set()
    domain_map = {"jazz":["jazz","improvisation"],"electronic":["electronic","idm","glitch","ambient","drone","synth"],"world":["world","african","asian","latin","folk","india","oriental"],"classical":["classical","chamber","minimalist","orchestral","solo","piano"]}
    for t in tags:
        for d, kws in domain_map.items():
            if any(k in t for k in kws): domains.add(d)
    if len(domains) < 2:
        for d, kws in domain_map.items():
            if any(k in el for k in kws): domains.add(d)
    cdb = max(0, len(domains) - 1) if len(domains) > 1 else 0
    
    # REG: scan excerpt for location names, not just tags
    combined_text = ",".join(tags) + " " + el + " " + (r.get("artist","") or "").lower()
    reg_kw_high = ["southeast asia","south america","middle east","central asia"]
    reg_kw_low = ["africa","latin","argentina","brazil","india","palestine","turkey","iran","japan","korea","thailand","mexico","cuba","morocco","egypt","chile","colombia","indonesia","china"]
    reg = 2 if any(kw in combined_text for kw in reg_kw_high) else (1 if any(kw in combined_text for kw in reg_kw_low) else 0)
    
    # MP: mainstream penalty (unchanged)
    mp = 0
    if all(k in el for k in ["pop","mainstream"]): mp = 3
    elif "pop" in el and "experimental" not in el and "avant" not in el: mp = 2
    elif "mainstream" in el and "experimental" not in el: mp = 2 if "indie" in el else 1
    
    # DR: synth/dungeon downgrade (unchanged)
    dr = 0
    if "synthwave" in tags_str or "retrowave" in tags_str:
        has_novelty = any(k in el for k in ["innovative","modern","experimental","composition","texture","design"])
        if not has_novelty:
            if all(k in el for k in ["retro","nostalgic"]): dr += 1
            if "vibes" in el and "sound" not in el and "textur" not in el: dr += 1
    if "dungeon synth" in tags_str or "dark ambient" in tags_str:
        has_detail = any(k in el for k in ["texture","layer","narrative","worldbuilding","composition","ritual"])
        if not has_detail and ("lo-fi" in el or "noise" in el): dr += 1
    
    pen = 1 if cq <= 1 and tm < 3 else 0
    return max(0, cq + tm + nov + cdb + reg - mp - dr - pen)

# ── 执行评分 ───────────────────────────────────────────────────
for r in reviews:
    r["total_score"] = score_review(r, r.get("_site", "unknown"))

scored = sorted(reviews, key=lambda x: x["total_score"], reverse=True)
passed = [r for r in scored if r["total_score"] >= 6]
print(f"Passed (>=6): {{len(passed)}}")

# ── 中文推荐总结：将英文原文浓缩为1-2句中文核心推荐 ──────────────────────────
import os
import sys
import json

# 调用 MiniMax API 做中文总结
MINIMAX_CN_API_KEY = os.environ.get("MINIMAX_CN_API_KEY", "")
# Also try reading from .env file directly
if not MINIMAX_CN_API_KEY:
    try:
        with open("/home/liyifan/.hermes/.env") as _envf:
            for _line in _envf:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "MINIMAX_CN_API_KEY" in _line:
                    MINIMAX_CN_API_KEY = _line.split("=", 1)[1].strip().strip("'"").strip()
                    break
    except:
        pass
MINIMAX_API_URL = "https://api.minimaxi.com/v1/chat/completions"

def summarize_cn(excerpt, artist_album, tags_raw_str=""):
    if not excerpt or excerpt.strip() == "":
        return "值得关注的前卫实验音乐作品。"
    
    # 截断太长的 excerpt
    text = excerpt.strip()
    if len(text) > 1000:
        text = text[:1000] + "..."
    
    # 拼接prompt，避免全角标点语法问题
    prompt_lines = [
        "你是一位专业华语乐评人。用1-2句简洁的中文总结这张专辑的核心特点：艺人是谁、什么声音风格、最亮眼之处。不要空话套话。",
        "",
        "专辑: " + artist_album,
        "",
        "英文原文:",
        text,
        "",
        "中文总结(1-2句): "
    ]
    prompt = "\n".join(prompt_lines)
    
    headers = {
        "Authorization": f"Bearer {MINIMAX_CN_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "MiniMax-M2.7",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }
    
    try:
        import urllib.request
        req = urllib.request.Request(MINIMAX_API_URL, json.dumps(data).encode('utf-8'), headers)
        with urllib.request.urlopen(req, timeout=30) as f:
            resp = json.load(f)
        result = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if result:
            # Strip <think>...</think> thinking block from MiniMax output
            import re
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
            return result.strip()
        else:
            # fallback: 用原来的关键词方法
            return gen_cn_fallback_v1(excerpt, artist_album, tags_raw_str)
    except Exception as e:
        print(f"Summarization API error: {e}, fallback to keywords")
        return gen_cn_fallback_v1(excerpt, artist_album, tags_raw_str)

# Fallback：关键词方法，如果API调用失败
def gen_cn_fallback_v1(excerpt_text, artist_album_str, tags_raw_str=""):
    excerpt = excerpt_text or ""
    artist_album = artist_album_str or ""
    tags_raw = tags_raw_str or ""
    tags_str = tags_raw.lower() if isinstance(tags_raw,str) else " ".join(tags_raw).lower()
    parts = []
    el = excerpt.lower()
    if "field recording" in tags_str: parts.append("实地录音素材构建声音地景")
    if any(k in tags_str for k in ["drone","ambient"]): parts.append("低频嗡鸣与氛围纹理")
    if any(k in tags_str for k in ["idm","glitch","electronic"]): parts.append("IDM/glitch 结构与电子音色设计")
    if any(k in tags_str for k in ["experimental","avant-garde"]): parts.append("前卫实验与解构手法")
    if any(k in tags_str for k in ["jazz","improvisation"]): parts.append("即兴爵士语汇")
    if any(k in tags_str for k in ["noise","industrial"]): parts.append("噪音/工业粗粝质感")
    if any(k in tags_str for k in ["classical","minimalist","chamber"]): parts.append("古典极简主义与室内乐语汇")
    if any(k in tags_str for k in ["world","african","asian","latin"]): parts.append("世界音乐元素")
    if any(k in tags_str for k in ["dark ambient","dungeon synth","darksynth"]): parts.append("暗黑氛围与仪式性声响")
    if "ritual" in el: parts.append("仪式性的声音进程")
    if "layer" in el or "texture" in el: parts.append("多层纹理堆叠")
    if "dark" in el or "horror" in el: parts.append("暗黑声景与心理张力")
    if "improvis" in el: parts.append("即兴演奏的现场能量")
    if "dungeon synth" in tags_str: parts.append("地下迷宫氛围与幻想叙事")
    if not parts: parts = ["值得关注的前卫实验声响"]
    return "；".join(parts[:3])

# ── 生成 markdown ─────────────────────────────────────────────
lines = [
    f"# Daily Music Recommendations — {DATE}\n",
    f"*Generated {{TODAY.isoformat()}} · {{len(reviews)}} reviews · {{len(passed)}} passed filter (≥6/10)*\n"
]
top = [r for r in scored if r["total_score"] >= 11]
mid = [r for r in scored if 8 <= r["total_score"] <= 10]
low = [r for r in scored if 6 <= r["total_score"] < 8]
if top:
    lines.append("## ★10+ — Top Picks\n")
    for r in top:
        artist_album = "{r['album']} — {r['artist']}".format(r=r)
        lines.append("**{r['album']} — {r['artist']}** [★{r['total_score']}], {r.get('source','unknown')}".format(r=r))
        lines.append("[阅读原文 →]({r.get('url','#')})".format(r=r))
        summary = summarize_cn(r.get('excerpt',''), artist_album, r.get('tags',''))
        lines.append("> 🔶 **中文总结**: {}\n".format(summary))
        lines.append("> {}".format(r.get('excerpt','')))
        lines.append("")
if mid:
    lines.append("## ★8-9 — Notable\n")
    for r in mid:
        artist_album = "{r['album']} — {r['artist']}".format(r=r)
        lines.append("**{r['album']} — {r['artist']}** [★{r['total_score']}], {r.get('source','unknown')}".format(r=r))
        lines.append("[阅读原文 →]({r.get('url','#')})".format(r=r))
        summary = summarize_cn(r.get('excerpt',''), artist_album, r.get('tags',''))
        lines.append("> 🔶 **中文总结**: {}\n".format(summary))
        lines.append("> {}".format(r.get('excerpt','')))
        lines.append("")
if low:
    lines.append("## ★6-7 — 此外值得关注\n")
    for r in low:
        artist_album = "{r['album']} — {r['artist']}".format(r=r)
        lines.append("**{r['album']} — {r['artist']}** [★{r['total_score']}], {r.get('source','unknown')}".format(r=r))
        lines.append("[阅读原文 →]({r.get('url','#')})".format(r=r))
        summary = summarize_cn(r.get('excerpt',''), artist_album, r.get('tags',''))
        lines.append("> 🔶 **中文总结**: {}\n".format(summary))
        lines.append("> {}".format(r.get('excerpt','')))
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
   git add 2026/%s/%s/ recommend/%s.md
   git add skills/music/music-daily-recs/SKILL.md bin/kanban-batch-scrape.py data/sites.json
   git commit -m "Daily: %s — %d reviews, %d passed filter"
   git push
   ```
   10. kanban_complete(summary="aggregated %d unique reviews, %d passed filter, recommend written to recommend/", metadata={"total": %d, "passed": %d})
   ```
"""

    from datetime import datetime
    date_obj = datetime.fromisoformat(DATE)
    git_month = date_obj.strftime("%Y-%m")
    N = len(all_task_ids)
    # passed count is unknown at template creation time — aggregator computes it
    passed_placeholder = 0
    
    # Save task IDs to temp file to avoid shell argument length limit with 40+ parents
    task_ids_file = f"/tmp/aggregator_parent_ids_{DATE}.json"
    with open(task_ids_file, 'w') as f:
        json.dump(all_task_ids, f)
    
    # Replace the all_task_ids placeholder with file read command in the body
    # The template still expects %d — we just leave it as is, actual loading from file
    agg_body = agg_body % (
        date_dir, date_dir, len(all_task_ids),
        date_dir, date_dir, DATE,
        date_dir, date_dir, date_dir, DATE,
        DATE, date_dir,
        git_month, DATE, DATE,
        DATE, len(all_task_ids), passed_placeholder,
        len(all_task_ids), passed_placeholder,
        len(all_task_ids), passed_placeholder
    )
    
    # Add code to load parent IDs from temp file
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