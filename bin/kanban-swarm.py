#!/usr/bin/env python3
"""
kanban-swarm.py — 只创建 5 个 Camoufox 探索 worker。无 Verifier / Synthesizer。

出货（merge / 评分 / 报告 / git push）走 bin/daily_pipeline.py，不进看板。
worker 失败不得挡住当天报告。

用法:
  python3 bin/kanban-swarm.py              # dry run
  python3 bin/kanban-swarm.py --confirm    # 创建任务
"""

import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SITES_FILE = str(Path(__file__).resolve().parent.parent / "data" / "sites.json")
OUTPUT_DIR = "/home/liyifan/music-record/2026"
TODAY = date.today()
DATE = TODAY.strftime("%Y-%m-%d")
MONTH = TODAY.strftime("%m")

# ── Hermes API 导入 ─────────────────────────────────────
_HERMES_HOME = os.path.expanduser("~/.hermes/hermes-agent")
if str(Path(_HERMES_HOME).resolve()) not in sys.path:
    sys.path.insert(0, str(Path(_HERMES_HOME).resolve()))

try:
    from hermes_cli import kanban_db as kb
    from hermes_cli import kanban_swarm as ks
except ImportError as e:
    print(f"❌ 无法导入 Hermes API: {e}", file=sys.stderr)
    sys.exit(1)


# ── 数据模型 ─────────────────────────────────────────────
@dataclass(frozen=True)
class SwarmWorkerSpec:
    profile: str
    title: str
    body: str
    skills: list[str] = field(default_factory=list)
    priority: int = 0
    max_runtime_seconds: Optional[int] = None


# Sites that have a dedicated HTML scraper in bin/ (priority over Camoufox).
# This is the post-priority-resolution list — every site in HTML_SCRIPT_IDS
# has its own scrape_*.py in bin/, so it is *not* assigned a Camoufox worker.
# ⚠️ MUST stay in sync with scrape_html_parallel.py: SCRIPTS list.
# If you add a new scrape_<site>.py, update BOTH lists (or the site will be
# double-scraped: once by HTML layer, once by Camoufox worker).
# Sites with has_rss=True go to fast-rss-scrape.py and must NOT be in either list.
HTML_SCRIPT_IDS = frozenset({
    "all_about_jazz",              # scrape_all_about_jazz.py
    "bandwagon_asia",              # scrape_bandwagon_asia.py
    "dark_entries_be",             # scrape_dark_entries.py
    "downbeat",                    # scrape_downbeat.py
    "free_jazz_blog",              # scrape_free_jazz_blog.py
    "hear65",                      # scrape_hear65.py
    "jazz_trail",                  # scrape_jazz_trail.py
    "mixmag_asia",                 # scrape_mixmag_asia.py
    "musique_machine",             # scrape_musique_machine.py
    "resident_advisor",            # scrape_resident_advisor.py
    "roots_world",                 # scrape_roots_world.py
    "sea_of_tranquility",          # scrape_sea_of_tranquility.py
    "songlines",                   # scrape_songlines.py
    "squids_ear",                  # scrape_squids_ear.py
    "strangely_isolated_place",    # scrape_strangely_isolated_place.py
    "mikiki",              # scrape_mikiki.py
    "progressor",          # scrape_progressor.py (direct HTTP; Camoufox TLS incompatible)
})


def get_sites():
    """Load sites that must be scraped with Camoufox (post-priority-resolution).

    Selection rule (priority order RSS > HTML > Camoufox):
      1. RSS  — sites with has_rss=True go to fast-rss-scrape.py
      2. HTML — sites in HTML_SCRIPT_IDS go to bin/scrape_<id>.py
      3. Camoufox — everything left that has crawl_strategy=playwright_headless
                    and is not skipped, and has no RSS, and is not in HTML_SCRIPT_IDS

    Returns the active Camoufox sites (currently 5: boomkat, jazztokyo, musicircus,
    point_of_departure, wild_city).
    """
    with open(SITES_FILE) as f:
        d = json.load(f)
    out = []
    for s in d["sites"]:
        if s.get("crawl_strategy") == "skip":
            continue
        if s.get("skipped"):
            continue
        if s.get("has_rss") and s.get("rss_url"):
            continue  # RSS path
        if s.get("id") in HTML_SCRIPT_IDS:
            continue  # HTML script path
        # Anything reaching here is the Camoufox tail.
        out.append(s)
    return out


BOOMKAT_EARLY_EXIT = """\
🚨 CF 拦截快速退出（Boomkat 专用）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Boomkat 每次新 tab 都会触发 Cloudflare Turnstile 隐形验证码，
会在 ~5-15s 后自动解除，但如果 IP 段/ASN 被标记则永远不解。

步骤：
1. 创建 Camoufox tab 访问 {url}
2. 等待 15 秒
3. 用以下 JS 检查是否仍在 CF challenge 页面：
   document.title + '|' + document.querySelectorAll('.listing2__product').length
4. 如果 title 含 "Just a moment" 或 products==0：
   → 立即写入 {out_file} = {{"meta":{{"total":0,"scraped_at":"...","cutoff_date":"36h前","cf_blocked":true,"site":"boomkat"}},"items":[]}}
   → kanban_complete(summary="boomkat CF blocked, 0 items", metadata={{"site":"boomkat","count":0,"cf_blocked":true}})
   → 立即停止，不要再开新 tab，不要重试
5. 如果 title 正常且 products>0：继续正常抓取流程
"""

def build_scraper_body(site, date_dir):
    """Build the scraper task body for one site.

    Worker is invoked with --days 1.5 explicitly so the cutoff is enforced by
    the scraper itself, not by the worker's own reading of the body. The
    body also instructs the worker to *check* for an RSS feed first — if found,
    the worker should produce a "skipped: rss_available" status instead of
    opening a browser (this enforces the RSS > HTML > Camoufox priority
    order at the worker level).
    """
    sid = site.get("id", site["name"].lower().replace(" ", "_"))
    name = site["name"]
    url = site.get("url") or site.get("reviews_url") or site.get("homepage", "")
    rss_url = site.get("rss_url", "") or ""
    strategy = site.get("crawl_strategy", "playwright_headless")
    tags = ", ".join(site.get("tags", []))
    out_file = f"{date_dir}/{sid}_reviews.json"

    rss_check_block = ""
    if rss_url:
        rss_check_block = f"""\
0. RSS 优先检查（必做）→ 命中直接退出：
   curl -fsS --max-time 10 {rss_url} | python3 bin/fast-rss-scrape.py --days 1.5 --site {sid} -
   如果该 feed 里有 ≥1 条近 36h 文章 → 把 JSON 写到 {out_file}，跳过浏览器
   如果 feed 空/超时/出错 → 继续 Step 1 浏览器
"""

    # Boomkat gets its own early-exit CF checkpoint
    cf_early_exit = BOOMKAT_EARLY_EXIT.format(url=url, out_file=out_file) if sid == "boomkat" else ""

    empty_protocol = f"""\
🚨 空结果协议（必须遵守，比抓到数据更优先）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
窗口内 0 条 / CF / paywall / 站点挂 / 进程要死：
1. 立刻写入 {out_file} = {{\"meta\":{{\"total\":0,\"scraped_at\":\"...\",\"cutoff_date\":\"36h前\",\"site\":\"{sid}\"}},\"items\":[]}}
2. kanban_complete(summary=\"scraped 0 items from {name}\", metadata={{\"site\":\"{sid}\",\"count\":0}})
3. 停。禁止换 URL、禁止重写脚本、禁止再确认、禁止 kanban_block。
JazzTokyo 月刊 0 条是正常结果，不是失败。
"""

    return f"""**{name}** · {url} · {strategy} · {tags}
RSS: {rss_url or "(none)"}

🔒 约束
━━━━━━━━━━━━━━━━
- 时间窗口：1.5 天 = 36 小时，硬约束。CLI 必须传 --days 1.5
- RSS 优先：先 curl + feedparser，有近期条目就不开浏览器
- Cookie 墙：navigate 后点击 Accept/Agree
- 非音乐过滤：跳过 (BLU-RAY)/(UHD)/(VOD)/(DVD)
- 特稿/访谈 → type: feature, score: null
- Paywall/CF → 走空结果协议，不要 kanban_block
- 禁止 kanban_block。任何结局都必须 kanban_complete。

❌ 禁止
━━━━━━━━━━━━━━━━
- 禁止写 Python 脚本测日期逻辑（模板里的 cutoff 是正确的）
- 禁止 RSS 有数据还开浏览器交叉验证
- 禁止翻超过前 2 页列表页
- 禁止自行计算 cutoff 日期（直接用 --days 1.5）
- 日志超过 100 行说明你在过度分析，超过 300 行说明你有问题
- Boomkat 禁止：CF 拦截后继续开新 tab 重试（直接用早期退出）
- 禁止 kanban_block

{empty_protocol}{rss_check_block}{cf_early_exit}✅ 步骤
━━━━━━━━━━━━━━━━
1. Camoufox 浏览器访问列表页，只翻前 2 页
2. Cookie 墙 → 检查并点击 Accept/Agree，等 1 秒
3. 提取：album, artist, score, url, source, pub_date, excerpt, body, site_id, crawl_status, type
4. 36 小时外停止翻页
5. 非音乐过滤：跳过含 (BLU-RAY)/(UHD)/(VOD)/(DVD) 条目
6. 写入 {out_file}（0 条也必须写 {{meta, items:[]}}）
7. kanban_complete(summary="scraped N items from {name}", metadata={{"site": "{sid}", "count": N, "hours_scanned": "36"}})

📦 输出格式
━━━━━━━━━━━━━━━━
写入 {out_file}，JSON 格式：
{{"meta": {{"total": N, "scraped_at": "...", "cutoff_date": "36h前"}},
  "items": [
    {{ "album", "artist", "score", "url", "source", "pub_date", "tags", "excerpt", "body", "site_id", "crawl_status", "type" }}
  ]
}}
type: "review" | "feature" | "tracklist"
❗ 必须包含 body 字段（全文正文，不截断）
❗ 必须使用 {{meta, items}} 外包装，不是裸数组
"""


WORKER_MAX_RUNTIME = 1200  # 20 min; dispatcher kills then retries, then blocks. 出货不等它。


def _swarm_context(root_id: str, goal: str) -> str:
    return (
        "\n\n## Swarm protocol\n"
        f"- Swarm root / shared blackboard: `{root_id}`.\n"
        "- Put machine-readable facts in completion metadata.\n"
        "- 禁止 kanban_block。0 条也要写空 JSON 然后 kanban_complete。\n"
        "- 出货不依赖本任务。daily_pipeline.py 已经/将会独立 merge+评分+push。\n"
        f"- Goal: {goal.strip()}\n"
    )


def idempotency_key_for_today():
    """Generate idempotency key based on today's date."""
    return f"music-recs-camo-{DATE}"


def create_swarm_graph(
    conn,
    *,
    goal: str,
    workers: list[SwarmWorkerSpec],
    created_by: str = "music-orchestrator",
    tenant: str = "music",
    workspace_kind: str = "dir",
    workspace_path: str,
    priority: int = 0,
    idempotency_key: str,
) -> dict:
    """Create root + Camoufox workers only. No verifier, no synthesizer."""

    existing_root_id = None
    for task in kb.list_tasks(conn, tenant=tenant, include_archived=True):
        if task.idempotency_key == idempotency_key:
            existing_root_id = task.id
            break

    if existing_root_id:
        bb = ks.latest_blackboard(conn, existing_root_id)
        topo = bb.get("topology", {})
        if isinstance(topo, dict) and topo.get("worker_ids"):
            print(f"  🗂️  Idempotency hit: reusing existing swarm {existing_root_id[:12]}...", file=sys.stderr)
            return {
                "root_id": existing_root_id,
                "worker_ids": topo["worker_ids"],
            }

    root_title = f"Camoufox: music-recs {DATE}"
    root_body = (
        "Camoufox 探索根卡片。出货走 daily_pipeline.py，本图不含 Verifier/Synthesizer。\n\n"
        f"目标:\n{goal}"
    )
    root_id = kb.create_task(
        conn,
        title=root_title,
        body=root_body,
        assignee=created_by,
        created_by=created_by,
        tenant=tenant,
        priority=priority,
        idempotency_key=idempotency_key,
        workspace_kind=workspace_kind,
        workspace_path=workspace_path,
        skills=["kanban-orchestrator"],
    )

    kb.complete_task(
        conn,
        root_id,
        summary="Camoufox workers planned; shipping is daily_pipeline.py.",
        metadata={
            "kind": "music_camoufox_workers",
            "goal": goal,
            "worker_count": len(workers),
        },
    )

    context = _swarm_context(root_id, goal)

    worker_ids = []
    for spec in workers:
        wid = kb.create_task(
            conn,
            title=spec.title,
            body=spec.body + context,
            assignee=spec.profile,
            created_by=created_by,
            parents=[root_id],
            tenant=tenant,
            priority=spec.priority or priority,
            workspace_kind=workspace_kind,
            workspace_path=workspace_path,
            skills=spec.skills or None,
            max_runtime_seconds=spec.max_runtime_seconds,
        )
        worker_ids.append(wid)

    result = {
        "root_id": root_id,
        "worker_ids": worker_ids,
    }
    ks.post_blackboard_update(
        conn,
        root_id,
        author=created_by,
        key="topology",
        value=result | {"goal": goal},
    )

    return result


def main():
    confirm = "--confirm" in sys.argv
    sites = get_sites()
    print(f"Active sites: {len(sites)}")
    for s in sites:
        print(f"  {s['name']}")
    print()

    if not confirm:
        print("Dry run. Pass --confirm to create tasks.")
        sys.exit(0)

    date_dir = f"{OUTPUT_DIR}/{MONTH}/{DATE}"
    os.makedirs(date_dir, exist_ok=True)

    workers = []
    for site in sites:
        name = site["name"]
        title = f"scrape: {name}"
        body = build_scraper_body(site, date_dir)
        workers.append(SwarmWorkerSpec(
            profile="scraper",
            title=title,
            body=body,
            skills=["kanban-worker"],
            max_runtime_seconds=WORKER_MAX_RUNTIME,
        ))

    goal = f"Camoufox 探索 {DATE}: {len(sites)} 站写 *_reviews.json。出货不依赖这些 worker。"
    idempotency_key = idempotency_key_for_today()
    workspace = f"{date_dir}"

    print(f"🏗  Creating Camoufox workers via Hermes API: {len(workers)}")
    print(f"   Workspace: dir:{workspace}")
    print(f"   Idempotency: {idempotency_key}")
    print(f"   max_runtime_seconds: {WORKER_MAX_RUNTIME}")
    print("   No verifier / synthesizer")

    with kb.connect_closing() as conn:
        result = create_swarm_graph(
            conn,
            goal=goal,
            workers=workers,
            created_by="music-orchestrator",
            tenant="music",
            workspace_kind="dir",
            workspace_path=workspace,
            priority=0,
            idempotency_key=idempotency_key,
        )

    root_id = result["root_id"]
    worker_ids = result["worker_ids"]

    print(f"\n  Root:       {root_id}")
    print(f"  Workers:    {len(worker_ids)} created")
    print("\n✅ Camoufox workers created. Shipping is daily_pipeline.py.")


if __name__ == "__main__":
    main()