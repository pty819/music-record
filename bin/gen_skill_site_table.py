#!/usr/bin/env python3
"""Rebuild the SKILL.md site-roster section from sites.json + layer code.

Single source of truth for *membership*:
  RSS      = has_rss AND rss_url
  HTML     = scrape_html_parallel.py SCRIPTS  (must equal HTML_SCRIPT_IDS)
  Camoufox = kanban-swarm.get_sites() remainder
  skip     = in sites.json but in none of the three layers

Do not hand-edit the generated block in SKILL.md. Regenerate:

  python3 bin/gen_skill_site_table.py --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES_JSON = ROOT / "data" / "sites.json"
HTML_PY = ROOT / "bin" / "scrape_html_parallel.py"
SWARM_PY = ROOT / "bin" / "kanban-swarm.py"
DEFAULT_SKILL = Path.home() / ".hermes/skills/music/music-daily-recs/SKILL.md"

BEGIN = "<!-- BEGIN GENERATED SITES -->"
END = "<!-- END GENERATED SITES -->"

# Operational remarks that are not in sites.json notes. Membership still
# comes from config+code; this dict only fills the 备注 column.
HTML_REMARKS = {
    "all_about_jazz": "Cloudflare 列表页",
    "bandwagon_asia": "新加坡/东南亚",
    "dark_entries_be": "暗潮/哥特/工业",
    "downbeat": "爵士；月刊，1.5d 窗口经常 0 条",
    "free_jazz_blog": "自由爵士/先锋",
    "hear65": "新加坡本地",
    "jazz_trail": "--max-pages 3 控速",
    "mixmag_asia": "列表页 + excerpt",
    "mikiki": "日本音乐媒体",
    "musique_machine": "电影/音乐混合",
    "resident_advisor": "Cloudflare",
    "roots_world": "curl 直连",
    "sea_of_tranquility": "urllib 直连，早停 5 条",
    "songlines": "180s timeout；详情页 paywall",
    "squids_ear": "squidco.com/ear/；依赖 amer1 出口",
    "strangely_isolated_place": "urllib 优先",
}

CAMO_REMARKS = {
    "boomkat": "Cloudflare ASN 封锁，脚本调 Camoufox REST API",
    "point_of_departure": "JS 渲染。Feature 无 Artist/Album 头 → parse_feature_page()。详见 references/pod-feature-unknown-album.md",
    "progressor": "冷门 prog/fusion，无独立 scrape 脚本",
    "wild_city": "印度/南亚电子，脚本调 Camoufox REST API",
    "jazztokyo": "日本爵士，需 JS 渲染",
    "musicircus": "日本先锋/即兴音乐",
}

RSS_FLAGS = {
    "fluid_radio": "archive_pick",
    "truth_and_lies_music": "Squarespace RSS",
    "world_music_central": "ex-HTML",
}


def _parse_scripts(text: str) -> list[tuple[str, str]]:
    """Return [(script_stem, site_id), ...] from SCRIPTS = [...]."""
    m = re.search(r"^SCRIPTS = \[(.*?)\]", text, re.S | re.M)
    if not m:
        sys.exit("ERROR: SCRIPTS list not found in scrape_html_parallel.py")
    return re.findall(r'\("(scrape_\w+)",\s*"(\w+)"', m.group(1))


def _parse_html_script_ids(text: str) -> set[str]:
    m = re.search(r"HTML_SCRIPT_IDS = frozenset\(\{(.*?)\}\)", text, re.S)
    if not m:
        sys.exit("ERROR: HTML_SCRIPT_IDS not found in kanban-swarm.py")
    return set(re.findall(r'"(\w+)"', m.group(1)))


def load_layers() -> dict:
    sites = json.loads(SITES_JSON.read_text())["sites"]
    by_id = {s["id"]: s for s in sites}
    scripts = _parse_scripts(HTML_PY.read_text())
    html_ids = [sid for _, sid in scripts]
    html_set = set(html_ids)
    swarm_ids = _parse_html_script_ids(SWARM_PY.read_text())
    if html_set != swarm_ids:
        sys.exit(
            f"ERROR: SCRIPTS {sorted(html_set)} != HTML_SCRIPT_IDS {sorted(swarm_ids)}"
        )

    rss, camoufox, skip = [], [], []
    for s in sites:
        sid = s["id"]
        if s.get("has_rss") and s.get("rss_url"):
            rss.append(s)
            continue
        if sid in html_set:
            continue  # counted via scripts order
        if s.get("crawl_strategy") == "skip" or s.get("skipped"):
            skip.append(s)
            continue
        camoufox.append(s)

    # HTML sites that exist in SCRIPTS but not sites.json
    missing_html = [sid for sid in html_ids if sid not in by_id]
    if missing_html:
        sys.exit(f"ERROR: HTML SCRIPTS not in sites.json: {missing_html}")

    html = [by_id[sid] for sid in html_ids]
    uncovered = [
        s
        for s in sites
        if s["id"] not in {x["id"] for x in rss}
        and s["id"] not in html_set
        and s["id"] not in {x["id"] for x in camoufox}
        and s["id"] not in {x["id"] for x in skip}
    ]
    skip.extend(uncovered)

    return {
        "all": sites,
        "rss": rss,
        "html": html,
        "html_scripts": scripts,
        "camoufox": camoufox,
        "skip": skip,
    }


def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def render(layers: dict) -> str:
    n_all = len(layers["all"])
    n_rss = len(layers["rss"])
    n_html = len(layers["html"])
    n_camo = len(layers["camoufox"])
    n_skip = len(layers["skip"])
    if n_rss + n_html + n_camo + n_skip != n_all:
        sys.exit(
            f"ERROR: layer sum {n_rss}+{n_html}+{n_camo}+{n_skip} != {n_all}"
        )

    rss_ids = ", ".join(
        (
            f"**{s['id']} ({RSS_FLAGS[s['id']]})**"
            if s["id"] in RSS_FLAGS
            else s["id"]
        )
        for s in layers["rss"]
    )

    html_rows = []
    script_by_id = {sid: stem for stem, sid in layers["html_scripts"]}
    for s in layers["html"]:
        sid = s["id"]
        script = f"{script_by_id[sid]}.py"
        remark = HTML_REMARKS.get(sid) or (s.get("notes") or "")
        html_rows.append(f"| {sid} | {script} | {_esc(remark)} |")

    camo_rows = []
    for s in layers["camoufox"]:
        sid = s["id"]
        remark = CAMO_REMARKS.get(sid) or (s.get("notes") or "")
        camo_rows.append(f"| {sid} | {_esc(remark)} |")

    skip_ids = ", ".join(s["id"] for s in layers["skip"]) or "（无）"

    camo_names = ", ".join(s["id"] for s in layers["camoufox"])

    lines = [
        BEGIN,
        f"<!-- generated by bin/gen_skill_site_table.py from data/sites.json. do not hand-edit. -->",
        "",
        f"站点分发（**{n_all} 站 = {n_rss} RSS + {n_html} HTML + {n_camo} Camoufox + {n_skip} skip**）。",
        "名单由 `python3 bin/gen_skill_site_table.py --write` 从 `data/sites.json` + `SCRIPTS` / `get_sites()` 生成，禁止手写增删。",
        "",
        "优先级：RSS > HTML > Camoufox > skip。每个站只走一层。",
        "",
        "| 层 | 数量 | 实现 |",
        "|---|---|---|",
        f"| RSS | {n_rss} | `fast-rss-scrape.py` — `has_rss=True AND rss_url` 非空 |",
        f"| HTML | {n_html} | `scrape_html_parallel.py` — `SCRIPTS`（须 = `HTML_SCRIPT_IDS`） |",
        f"| Camoufox | {n_camo} | `kanban-swarm.py:get_sites()` — 剩余站 |",
        f"| skip | {n_skip} | 三层都未覆盖：{skip_ids} |",
        "",
        "**代码位置**：",
        "- RSS 筛选：`bin/fast-rss-scrape.py:load_sites()`",
        "- HTML/Camoufox 分配：`bin/kanban-swarm.py:HTML_SCRIPT_IDS` + `get_sites()`",
        "- ⚠️ `SCRIPTS` 与 `HTML_SCRIPT_IDS` 必须保持一致，否则站点会被双轨抓取（详见 Pitfalls）",
        "- 站点表再生：`python3 bin/gen_skill_site_table.py --write`",
        "",
        f"## {n_rss} RSS",
        "",
        rss_ids,
        "",
        f"## {n_html} HTML",
        "",
        "| 站 | 脚本 | 备注 |",
        "|---|---|---|",
        *html_rows,
        "",
        f"## {n_camo} Camoufox（kanban worker，需 Camoufox 服务）",
        "",
        f"当前：{camo_names}",
        "",
        "| 站 | 备注 |",
        "|---|---|",
        *camo_rows,
        "",
        f"## {n_skip} skip",
        "",
        skip_ids,
        "",
        END,
    ]
    return "\n".join(lines) + "\n"


def counts_for_frontmatter(layers: dict) -> dict:
    return {
        "n_all": len(layers["all"]),
        "n_rss": len(layers["rss"]),
        "n_html": len(layers["html"]),
        "n_camo": len(layers["camoufox"]),
        "n_skip": len(layers["skip"]),
    }


def patch_skill(skill_path: Path, block: str, counts: dict) -> None:
    text = skill_path.read_text()
    if BEGIN not in text or END not in text:
        sys.exit(f"ERROR: {skill_path} missing {BEGIN} / {END} markers")
    pre, rest = text.split(BEGIN, 1)
    _, post = rest.split(END, 1)
    # drop leftover newline after END so we don't stack blanks
    if post.startswith("\n"):
        post = post[1:]
    new = pre + block + post

    n_all, n_rss, n_html, n_camo, n_skip = (
        counts["n_all"],
        counts["n_rss"],
        counts["n_html"],
        counts["n_camo"],
        counts["n_skip"],
    )
    # Keep the YAML description in lockstep with generated counts.
    new = re.sub(
        r"每日巡检 \d+ 个音乐评论站（[^）]+）",
        f"每日巡检 {n_all} 个音乐评论站（{n_rss} RSS + {n_html} HTML + {n_camo} Camoufox + {n_skip} skip）",
        new,
        count=1,
    )
    new = re.sub(
        r"├─ Step 2: RSS    \(\d+\+?\d* 站,",
        f"├─ Step 2: RSS    ({n_rss} 站,",
        new,
        count=1,
    )
    new = re.sub(
        r"├─ Step 3: HTML   \(\d+ 站子进程并发",
        f"├─ Step 3: HTML   ({n_html} 站子进程并发",
        new,
        count=1,
    )
    skill_path.write_text(new)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="patch SKILL.md in place")
    ap.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    args = ap.parse_args()

    layers = load_layers()
    block = render(layers)
    counts = counts_for_frontmatter(layers)
    print(
        f"# {counts['n_all']} sites = "
        f"{counts['n_rss']} RSS + {counts['n_html']} HTML + "
        f"{counts['n_camo']} Camoufox + {counts['n_skip']} skip"
    )
    if not args.write:
        sys.stdout.write(block)
        return 0
    patch_skill(args.skill, block, counts)
    print(f"wrote {args.skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
