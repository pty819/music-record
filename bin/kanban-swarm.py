#!/usr/bin/env python3
"""
kanban-swarm.py — 使用 Kb Swarm API 创建音乐推荐抓取流程（无裸 SQLite）。

替代旧 kanban-batch-scrape.py（创建 21 个独立任务 + 1 个 aggregator）。
使用 Hermes 自身的 kanban_db.create_task() API，无需直连 SQLite。

架构：
  root planning card (complete 立即完成)
    ├─ worker 1..21: Camoufox 浏览器抓取 (ready, parent=root)
    └─ verifier: 合并+验证 (todo, parent=所有 worker)
         └─ synthesizer: 评分+报告+推送 (todo, parent=verifier)

用法:
  python3 bin/kanban-swarm.py              # dry run
  python3 bin/kanban-swarm.py --confirm    # 创建任务
"""

import json
import os
import subprocess
import sys
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SITES_FILE = "/home/liyifan/.minimax/music-sites/sites.json"
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


def get_sites():
    """Load non-RSS Camoufox sites."""
    with open(SITES_FILE) as f:
        d = json.load(f)
    return [
        s for s in d["sites"]
        if s.get("crawl_strategy") != "skip"
        and not s.get("skipped")
        and not s.get("has_rss")
    ]


def build_scraper_body(site, date_dir):
    """Build the scraper task body for one site."""
    sid = site.get("id", site["name"].lower().replace(" ", "_"))
    name = site["name"]
    url = site.get("url") or site.get("reviews_url") or site.get("homepage", "")
    strategy = site.get("crawl_strategy", "playwright_headless")
    tags = ", ".join(site.get("tags", []))
    out_file = f"{date_dir}/{sid}_reviews.json"

    return f"""**{name}** · {url} · {strategy} · {tags}

🔒 约束
━━━━━━━━━━━━━━━━
- 时间范围：只抓 36 小时内文章，超期停止
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
1. 检查 RSS → curl + feedparser，过滤 36 小时内条目
   - CDATA 全文用 summary 字段获取，strip HTML 取前 500 字
   - curl 超时（SSL 握手失败）→ 走 Camoufox 浏览器
2. 无 RSS → Camoufox 浏览器访问列表页，只翻前 2 页
3. Cookie 墙 → 检查并点击 Accept/Agree，等 1 秒
4. 提取：album, artist, score, url, source, pub_date, excerpt, type
5. 超 36 小时停止翻页
6. 非音乐过滤：跳过含 (BLU-RAY)/(UHD)/(VOD)/(DVD) 条目
7. kanban_complete

📦 输出格式
━━━━━━━━━━━━━━━━
写入 {out_file}，JSON 格式：
{{"meta": {{"total": N, "scraped_at": "...", "cutoff_date": "~36h前"}},
  "items": [
    {{ "album", "artist", "score", "url", "source", "pub_date", "tags", "excerpt", "body", "site_id", "crawl_status", "type" }}
  ]
}}
type: "review" | "feature" | "tracklist"
❗ 必须包含 body 字段（全文正文，不截断）
❗ 必须使用 {{meta, items}} 外包装，不是裸数组
kanban_complete(summary="scraped N items from {name}", metadata={{"site": "{sid}", "count": N, "hours_scanned": "36"}})"""


VERIFIER_BODY = """🔒 约束
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 严格按顺序执行 Step 1→2，一步不能少
- 每一步检查 exit code，失败则重试一次
- 只用 terminal 工具运行以下命令

✅ 步骤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: 合并所有抓取数据 → scraped_raw.json
cd /home/liyifan/music-record
python3 /home/liyifan/.local/bin/merge_scraped.py \\
  --date-dir "$(pwd)/2026/$(date +%m)/$(date +%Y-%m-%d)" \\
  -o scraped_raw.json

Step 2: 验证合并结果 — 必须通过才能放行
python3 -c "
import json
d = json.load(open('2026/$(date +%m)/$(date +%Y-%m-%d)/scraped_raw.json'))
items = d.get('items', []) if isinstance(d, dict) else d
assert len(items) > 0, '合并结果为空'
for i in items[:3]:
    assert 'site_id' in i, f'缺少 site_id 字段: {i.get(\"album\",\"?\")}[:30]'
print(f'✅ {len(items)} 条数据，质量检查通过')
"

🟢 Gate: 以上两步全部通过 → kanban_complete(metadata={"gate": "pass", "total_items": N})
🔴 Gate: 任一步失败 → kanban_block(reason="数据合并或验证失败，详情见日志")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
‼️ 仅执行以上步骤。完成本任务后不要执行评分/报告——那是 synthesizer 的工作。"""


SYNTHESIZER_BODY = """🔒 约束
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 严格按顺序执行 Step 1→2→3→4→5，一步不能少
- 每一步检查 exit code，失败则重试一次
- 只用 terminal 工具运行以下命令
- 不要调用 kanban_create / delegate_task / web_search

✅ 步骤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: 并发评分 + 中文总结 → processed.json
cd /home/liyifan/music-record
python3 bin/process_reviews.py \\
  --date-dir "2026/$(date +%m)/$(date +%Y-%m-%d)" \\
  -i scraped_raw.json \\
  -o processed.json \\
  --max-workers 5

验证: processed.json 存在且含 total_score + _cn_summary
如果 MiniMax rate limit (429)，重试一次；仍失败则跳过

Step 2: 生成推荐 markdown → recommend/{DATE}.md
python3 bin/generate_report.py \\
  --date-dir "2026/$(date +%m)/$(date +%Y-%m-%d)" \\
  -i processed.json \\
  --date "$(date +%Y-%m-%d)"

验证: recommend/$(date +%Y-%m-%d).md 存在

Step 3: git push 到 GitHub
cd /home/liyifan/music-record
rm -f "2026/$(date +%m)/$(date +%Y-%m-%d)"/*.py
git add -A "2026/$(date +%m)/$(date +%Y-%m-%d)" "recommend/$(date +%Y-%m-%d).md" \\
  bin/process_reviews.py bin/generate_report.py bin/merge_scraped.py bin/kanban-swarm.py
git commit -m "music-recs: $(date +%Y-%m-%d) daily recommendations (kanban swarm)" || true
git push origin main 2>&1

如果 git push 失败（GFW），记录错误但继续下一步

Step 4: Telegram 推送
读取 /home/liyifan/music-record/recommend/$(date +%Y-%m-%d).md 内容
如果 ≤4000 字符，用 send_message 发送全文到 Telegram Home 频道
如果 >4000 字符，发送前 30 行 + '...' + 完整推荐 GitHub 链接
如果 send_message 不可用（profile 没权限），跳过此步

Step 5: 归档本轮 scraper 任务
hermes kanban list | grep "done.*scrape:" | awk '{print $2}' | while read tid; do
  hermes kanban archive "$tid"
done

📌 注意: hermes kanban list 的输出格式是 {icon} {task_id} ...
     用 awk '{print $2}' 取 task_id，$1 是图标

Step 6: 完成任务
kanban_complete(summary="music-recs $(date +%Y-%m-%d): merge → score → report → push → telegram → archive")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
‼️ 仅执行以上步骤，不多做任何事。"""


def _swarm_context(root_id: str, goal: str) -> str:
    return (
        "\n\n## Swarm protocol\n"
        f"- Swarm root / shared blackboard: `{root_id}`.\n"
        "- Read sibling/parent handoffs from Kanban context before working.\n"
        "- Put machine-readable facts in completion metadata.\n"
        "- Put cross-worker notes on the root task using structured comments.\n"
        f"- Goal: {goal.strip()}\n"
    )


def idempotency_key_for_today():
    """Generate idempotency key based on today's date."""
    return f"music-recs-swarm-{DATE}"


def create_swarm_graph(
    conn,
    *,
    goal: str,
    workers: list[SwarmWorkerSpec],
    verifier_body: str,
    synthesizer_body: str,
    verifier_assignee: str = "scraper",
    synthesizer_assignee: str = "scraper",
    created_by: str = "music-orchestrator",
    tenant: str = "music",
    workspace_kind: str = "dir",
    workspace_path: str,
    priority: int = 0,
    idempotency_key: str,
) -> dict:
    """Create swarm DAG using Hermes kanban_db API (no raw SQL).

    Returns dict with root_id, worker_ids, verifier_id, synthesizer_id.
    Idempotent: if root with same idempotency_key exists, recovers topology.
    """

    # ── 1. Check idempotency ──
    # Look for an existing root task with this idempotency key
    existing_root_id = None
    for task in kb.list_tasks(conn, tenant=tenant, include_archived=True):
        if task.idempotency_key == idempotency_key:
            existing_root_id = task.id
            break

    if existing_root_id:
        # Try to recover topology from blackboard
        bb = ks.latest_blackboard(conn, existing_root_id)
        topo = bb.get("topology", {})
        if isinstance(topo, dict) and topo.get("worker_ids") and topo.get("verifier_id") and topo.get("synthesizer_id"):
            print(f"  🗂️  Idempotency hit: reusing existing swarm {existing_root_id[:12]}...", file=sys.stderr)
            return {
                "root_id": existing_root_id,
                "worker_ids": topo["worker_ids"],
                "verifier_id": topo["verifier_id"],
                "synthesizer_id": topo["synthesizer_id"],
            }

    # ── 2. Create root ──
    root_title = f"Swarm: music-recs {DATE}"
    root_body = (
        "Kanban Swarm v1 规划/根卡片。已完成，作为共享 blackboard 和审计锚点。\n\n"
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

    # Complete root immediately (parallel workers can start)
    kb.complete_task(
        conn,
        root_id,
        summary="Swarm topology planned; root remains the shared blackboard.",
        metadata={
            "kind": "kanban_swarm_v1",
            "goal": goal,
            "worker_count": len(workers),
        },
    )

    context = _swarm_context(root_id, goal)

    # ── 3. Create workers ──
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

    # ── 4. Create verifier ──
    verifier_id = kb.create_task(
        conn,
        title="Verify: merge + quality check",
        body=verifier_body + context,
        assignee=verifier_assignee,
        created_by=created_by,
        parents=worker_ids,  # parent-gated: waits for ALL workers
        tenant=tenant,
        priority=priority,
        workspace_kind=workspace_kind,
        workspace_path=workspace_path,
        skills=["kanban-worker"],
    )

    # ── 5. Create synthesizer ──
    synthesizer_id = kb.create_task(
        conn,
        title="Synthesize: score → report → push → Telegram → archive",
        body=synthesizer_body + context,
        assignee=synthesizer_assignee,
        created_by=created_by,
        parents=[verifier_id],  # parent-gated: waits for verifier
        tenant=tenant,
        priority=priority,
        workspace_kind=workspace_kind,
        workspace_path=workspace_path,
        skills=["kanban-worker"],
    )

    # ── 6. Post topology to blackboard ──
    result = {
        "root_id": root_id,
        "worker_ids": worker_ids,
        "verifier_id": verifier_id,
        "synthesizer_id": synthesizer_id,
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

    # ── Build workspace path ──
    date_dir = f"{OUTPUT_DIR}/{MONTH}/{DATE}"
    os.makedirs(date_dir, exist_ok=True)

    # ── Build worker specs ──
    workers = []
    for site in sites:
        sid = site.get("id", site["name"].lower().replace(" ", "_"))
        name = site["name"]
        title = f"scrape: {name}"
        body = build_scraper_body(site, date_dir)
        workers.append(SwarmWorkerSpec(
            profile="scraper",
            title=title,
            body=body,
            skills=["kanban-worker"],
        ))

    goal = f"音乐推荐抓取 {DATE}: {len(sites)} 个 Camoufox 站抓取 → 合并 → 评分 → 生成推荐 → 推送"
    idempotency_key = idempotency_key_for_today()
    workspace = f"{date_dir}"

    print(f"🏗  Creating swarm via Hermes API: {len(workers)} workers")
    print(f"   Workspace: dir:{workspace}")
    print(f"   Idempotency: {idempotency_key}")

    # ── Use Hermes kanban_db connection manager (same WAL as CLI) ──
    # NOTE: do NOT pass board= — this version of Hermes uses multiple kanban.db files
    # for boards and the dispatcher only watches the default board.
    with kb.connect_closing() as conn:
        result = create_swarm_graph(
            conn,
            goal=goal,
            workers=workers,
            verifier_body=VERIFIER_BODY,
            synthesizer_body=SYNTHESIZER_BODY,
            verifier_assignee="scraper",
            synthesizer_assignee="scraper",
            created_by="music-orchestrator",
            tenant="music",
            workspace_kind="dir",
            workspace_path=workspace,
            priority=0,
            idempotency_key=idempotency_key,
        )

    root_id = result["root_id"]
    worker_ids = result["worker_ids"]
    verifier_id = result["verifier_id"]
    synthesizer_id = result["synthesizer_id"]

    print(f"\n  Root:       {root_id}")
    print(f"  Workers:    {len(worker_ids)} created")
    print(f"  Verifier:   {verifier_id}")
    print(f"  Synthesizer: {synthesizer_id}")

    # Print role summaries
    print(f"\n📋 Role assignments:")
    print(f"   Verifier:   merge_scraped.py + quality check → gate pass/block")
    print(f"   Synthesizer: process_reviews → generate_report → git push → Telegram → archive")

    print(f"\n✅ Swarm created successfully!")
    print(f"   {len(worker_ids)} Camoufox scraper workers")
    print(f"   Cron session can exit — kanban handles the rest.")


if __name__ == "__main__":
    main()