#!/usr/bin/env python3
"""
Standalone aggregator for music daily recs pipeline.

Reads all *_reviews.json from --date-dir, dedup, scores, generates
Chinese summaries via MiniMax M2.7, writes aggregated.json,
filtered.json, and recommend/{DATE}.md.

Usage:
  python3 aggregate_reviews.py --date-dir /path/to/2026/05/2026-05-19 --date 2026-05-19
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime


def parse_args():
    p = argparse.ArgumentParser(description="Aggregate music reviews")
    p.add_argument("--date-dir", required=True, help="Absolute path to the date subdir (e.g. /home/liyifan/music-record/2026/05/2026-05-19)")
    p.add_argument("--date", required=True, help="Date string YYYY-MM-DD")
    p.add_argument("--no-summary", action="store_true", help="Skip LLM summarization (for testing)")
    return p.parse_args()


# ── LLM summarization ──────────────────────────────────────────

def _read_api_key():
    """Read MINIMAX_CN_API_KEY from env or .env file."""
    key = os.environ.get("MINIMAX_CN_API_KEY", "")
    if key:
        return key
    try:
        with open(os.path.expanduser("~/.hermes/.env")) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "MINIMAX_CN_API_KEY" in line:
                    return line.split("=", 1)[1].strip().strip("'\"").strip()
    except Exception:
        pass
    return ""


MINIMAX_CN_API_KEY = _read_api_key()


def summarize_cn(excerpt, artist_album, tags_raw_str=""):
    if not excerpt or excerpt.strip() == "":
        return "值得关注的前卫实验音乐作品。"

    text = excerpt.strip()
    if len(text) > 1000:
        text = text[:1000] + "..."

    prompt_lines = [
        "你是一位专业华语乐评人。用2-3句中文总结这张专辑的核心特点：说明艺人背景、专辑的声音风格、最亮眼的听感特点和值得关注之处。不要空话套话，给出具体信息。",
        "",
        "专辑: " + artist_album,
        "",
        "英文原文:",
        text,
        "",
        "请将最终的中文总结放在<summary>和</summary>标签之间，方便程序提取。"
    ]
    prompt = "\n".join(prompt_lines)

    try:
        import anthropic
        client = anthropic.Anthropic(
            api_key=MINIMAX_CN_API_KEY,
            base_url="https://api.minimaxi.com/anthropic",
        )
        message = client.messages.create(
            timeout=60,
            model="MiniMax-M2.7",
            max_tokens=30000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        result = ""
        for block in reversed(message.content):
            if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
                result = block.text
                break
        if result:
            match = re.search(r'<summary>(.*?)</summary>', result, flags=re.DOTALL)
            if match:
                result = match.group(1)
            return result.strip()
        else:
            return _gen_cn_fallback(excerpt, artist_album, tags_raw_str)
    except Exception as e:
        print(f"  [summarize] API error: {e}, fallback", file=sys.stderr)
        return _gen_cn_fallback(excerpt, artist_album, tags_raw_str)


def _gen_cn_fallback(excerpt_text, artist_album_str, tags_raw_str=""):
    excerpt = excerpt_text or ""
    tags_raw = tags_raw_str or ""
    tags_str = tags_raw.lower() if isinstance(tags_raw, str) else " ".join(tags_raw).lower()
    parts = []
    el = excerpt.lower()

    if "field recording" in tags_str:
        parts.append("实地录音素材构建声音地景")
    if any(k in tags_str for k in ["drone", "ambient"]):
        parts.append("低频嗡鸣与氛围纹理")
    if any(k in tags_str for k in ["idm", "glitch", "electronic"]):
        parts.append("IDM/glitch 结构与电子音色设计")
    if any(k in tags_str for k in ["experimental", "avant-garde"]):
        parts.append("前卫实验与解构手法")
    if any(k in tags_str for k in ["jazz", "improvisation"]):
        parts.append("即兴爵士语汇")
    if any(k in tags_str for k in ["noise", "industrial"]):
        parts.append("噪音/工业粗粝质感")
    if any(k in tags_str for k in ["classical", "minimalist", "chamber"]):
        parts.append("古典极简主义与室内乐语汇")
    if any(k in tags_str for k in ["world", "african", "asian", "latin"]):
        parts.append("世界音乐元素")
    if any(k in tags_str for k in ["dark ambient", "dungeon synth", "darksynth"]):
        parts.append("暗黑氛围与仪式性声响")
    if "ritual" in el:
        parts.append("仪式性的声音进程")
    if "layer" in el or "texture" in el:
        parts.append("多层纹理堆叠")
    if "dark" in el or "horror" in el:
        parts.append("暗黑声景与心理张力")
    if "improvis" in el:
        parts.append("即兴演奏的现场能量")
    if "dungeon synth" in tags_str:
        parts.append("地下迷宫氛围与幻想叙事")
    if not parts:
        parts = ["值得关注的前卫实验声响"]
    return "；".join(parts[:3])


# ── Scoring ────────────────────────────────────────────────────

SITE_TAGS = {
    "musique_machine": ["dark ambient", "industrial", "electroacoustic", "experimental", "noise"],
    "squids_ear": ["experimental", "electronic", "sound art", "avant-garde", "improvisation"],
    "igloo_magazine": ["experimental electronic", "idm", "ambient", "glitch", "electroacoustic"],
    "hhv_mag": ["electronic", "vinyl culture", "electroacoustic", "experimental"],
    "a_closer_listen": ["instrumental", "experimental", "ambient", "drone", "field recording"],
    "roots_world": ["world music", "roots", "folk", "traditional"],
    "world_music_central": ["world music", "traditional music", "world fusion", "experimental"],
    "free_jazz_blog": ["free jazz", "avant-jazz", "improvised music"],
    "the_quietus": ["experimental", "electronic", "jazz", "world", "avant-garde"],
    "jazz_trail": ["avant-garde jazz", "experimental", "improvisation"],
    "avant_music_news": ["experimental", "weird", "progressive", "avant-garde"],
    "all_about_jazz": ["jazz", "fusion", "avant-garde", "avant-jazz", "world"],
    "the_wire": ["experimental", "avant-garde", "free jazz", "electronic", "drone", "ambient", "world", "contemporary", "improvisation"],
}


def get_site_taste_baseline(site_id):
    st = SITE_TAGS.get(site_id, [])
    st_str = " ".join(st)
    score = 0
    if any(k in st_str for k in [
        "experimental", "avant-garde", "free jazz", "electroacoustic", "drone",
        "ambient", "idm", "glitch", "industrial", "noise", "improvisation",
        "sound art", "field recording"
    ]):
        score += 2
    if any(k in st_str for k in ["world", "folk", "electronic", "minimalist", "ritual", "weird"]):
        score += 1
    return min(2, score)


def score_review(r, site_id="musique_machine"):
    excerpt = r.get("excerpt", "") or r.get("summary", "") or ""
    tags_raw = r.get("tags", "") or r.get("genre", "") or ""
    tags_str = tags_raw.lower() if isinstance(tags_raw, str) else " ".join(t.lower() for t in tags_raw).lower()
    el = excerpt.lower()
    elen = len(excerpt)

    # CQ: logarithmic, capped at 3
    cq = min(3, elen // 150 + (1 if elen % 150 > 75 else 0)) if elen > 0 else 0

    # TM: 3-layer
    site_base = get_site_taste_baseline(site_id)
    avant_kw = [
        "experimental", "avant-garde", "free jazz", "electroacoustic", "drone",
        "ambient", "idm", "glitch", "industrial", "sound art", "modern composition",
        "field recording", "improvisation", "noise", "ritual", "dark ambient",
        "dungeon synth", "darksynth", "synthwave", "world fusion", "fusion"
    ]
    entry_tag_match = min(3, sum(1 for kw in avant_kw if kw in tags_str))
    excerpt_match = 0
    if entry_tag_match < 2:
        excerpt_kw = [
            "experimental", "avant-garde", "free jazz", "electroacoustic", "drone",
            "ambient", "idm", "glitch", "industrial", "noise", "field recording",
            "improvisation", "fusion"
        ]
        match_count = sum(1 for k in excerpt_kw if k in el)
        if match_count >= 2:
            excerpt_match = 1
    tm = min(5, site_base + entry_tag_match + excerpt_match)

    # NOV: expanded keyword list
    nov_kw = [
        "unique", "rare", "first", "unusual", "innovative", "cross-cultural",
        "world", "ritual", "exploration", "boundary", "genre-defying",
        "groundbreaking", "fusion", "breakthrough", "singular", "unconventional", "pushing"
    ]
    nov = min(3, sum(1 for kw in nov_kw if kw in el))

    # CDB: scan entry tags + excerpt
    domains = set()
    domain_map = {
        "jazz": ["jazz", "improvisation"],
        "electronic": ["electronic", "idm", "glitch", "ambient", "drone", "synth"],
        "world": ["world", "african", "asian", "latin", "folk", "india", "oriental"],
        "classical": ["classical", "chamber", "minimalist", "orchestral", "solo", "piano"],
    }
    for d, kws in domain_map.items():
        if any(k in tags_str for k in kws):
            domains.add(d)
    if len(domains) < 2:
        for d, kws in domain_map.items():
            if any(k in el for k in kws):
                domains.add(d)
    cdb = max(0, len(domains) - 1) if len(domains) > 1 else 0

    # REG: scan tags + excerpt + artist
    combined_text = tags_str + " " + el + " " + (r.get("artist", "") or "").lower()
    reg_kw_high = ["southeast asia", "south america", "middle east", "central asia"]
    reg_kw_low = [
        "africa", "latin", "argentina", "brazil", "india", "palestine", "turkey",
        "iran", "japan", "korea", "thailand", "mexico", "cuba", "morocco", "egypt",
        "chile", "colombia", "indonesia", "china"
    ]
    reg = 2 if any(kw in combined_text for kw in reg_kw_high) else (
        1 if any(kw in combined_text for kw in reg_kw_low) else 0
    )

    # MP: mainstream penalty
    mp = 0
    if all(k in el for k in ["pop", "mainstream"]):
        mp = 3
    elif "pop" in el and "experimental" not in el and "avant" not in el:
        mp = 2
    elif "mainstream" in el and "experimental" not in el:
        mp = 2 if "indie" in el else 1

    # DR: synth/dungeon downgrade
    dr = 0
    if "synthwave" in tags_str or "retrowave" in tags_str:
        has_novelty = any(k in el for k in ["innovative", "modern", "experimental", "composition", "texture", "design"])
        if not has_novelty:
            if all(k in el for k in ["retro", "nostalgic"]):
                dr += 1
            if "vibes" in el and "sound" not in el and "textur" not in el:
                dr += 1
    if "dungeon synth" in tags_str or "dark ambient" in tags_str:
        has_detail = any(k in el for k in ["texture", "layer", "narrative", "worldbuilding", "composition", "ritual"])
        if not has_detail and ("lo-fi" in el or "noise" in el):
            dr += 1

    pen = 1 if cq <= 1 and tm < 3 else 0
    return max(0, cq + tm + nov + cdb + reg - mp - dr - pen)


# ── Main ────────────────────────────────────────────────────────

def main():
    args = parse_args()
    date_dir = args.date_dir
    date_str = args.date

    if not os.path.isdir(date_dir):
        print(f"Error: date_dir not found: {date_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. Read all scraper JSON files
    all_files = sorted(f for f in os.listdir(date_dir) if f.endswith("_reviews.json"))
    reviews = []
    for fname in all_files:
        fpath = os.path.join(date_dir, fname)
        with open(fpath) as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            reviews.append(item)
            except json.JSONDecodeError as e:
                print(f"  [warn] JSON error in {fname}: {e}", file=sys.stderr)

    print(f"Loaded {len(reviews)} reviews from {len(all_files)} files")

    # 2. Dedup by (album+artist), keep highest score
    seen = {}
    for r in reviews:
        key = (r.get("album", ""), r.get("artist", ""))
        old = seen.get(key, {})
        if "score" not in old or (r.get("score") is not None and r.get("score", 0) > (old.get("score") or 0)):
            seen[key] = r
    reviews = list(seen.values())
    print(f"Deduplicated: {len(reviews)} unique")

    # 3. Score
    for r in reviews:
        r["total_score"] = score_review(r, r.get("_site", "unknown"))
    scored = sorted(reviews, key=lambda x: x["total_score"], reverse=True)
    passed = [r for r in scored if r["total_score"] >= 6]
    print(f"Passed (>=6): {len(passed)}")

    # 4. Generate Chinese summaries (only for passed items)
    print(f"Summarizing {len(passed)} items via MiniMax M2.7...")
    for i, r in enumerate(passed, 1):
        if args.no_summary:
            r["_cn_summary"] = "（摘要跳过）"
            continue
        album = r.get("album", "")
        artist = r.get("artist", "")
        artist_album = f"{album} — {artist}" if album and artist else (album or artist or "未知作品")
        sys.stdout.write(f"  [{i}/{len(passed)}] {artist_album[:50]}... ")
        sys.stdout.flush()
        r["_cn_summary"] = summarize_cn(
            r.get("excerpt", ""),
            artist_album,
            r.get("tags", "")
        )
        print(f"done ({len(r['_cn_summary'])} chars)")

    # 5. Write aggregated.json (all scored)
    agg_path = os.path.join(date_dir, "aggregated.json")
    with open(agg_path, "w") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)
    print(f"Wrote {agg_path}")

    # 6. Write filtered.json (>=6)
    filt_path = os.path.join(date_dir, "filtered.json")
    with open(filt_path, "w") as f:
        json.dump(passed, f, ensure_ascii=False, indent=2)
    print(f"Wrote {filt_path}")

    # 7. Generate markdown
    now = datetime.now()
    lines = [
        f"# Daily Music Recommendations — {date_str}\n",
        f"*Generated {now.isoformat()} · {len(reviews)} reviews · {len(passed)} passed filter (≥6/10)*\n"
    ]

    top = [r for r in scored if r["total_score"] >= 11]
    mid = [r for r in scored if 8 <= r["total_score"] <= 10]
    low = [r for r in scored if 6 <= r["total_score"] < 8]

    for group_title, group in [
        ("## ★10+ — Top Picks\n", top),
        ("## ★8-9 — Notable\n", mid),
        ("## ★6-7 — 此外值得关注\n", low),
    ]:
        if not group:
            continue
        lines.append(group_title)
        for r in group:
            album = r.get("album", "(unknown)")
            artist = r.get("artist", "(unknown)")
            source = r.get("source", "") or r.get("_site", "") or r.get("site_id", "") or "unknown"
            url = r.get("url", "#")
            summary = r.get("_cn_summary", "")
            rtype = r.get("type", "review")
            prefix = ""
            if rtype == "feature":
                prefix = "▸ [FEATURE] "
            elif rtype == "tracklist":
                prefix = "▸ [TRACKLIST] "

            lines.append(f"**{prefix}{album} — {artist}** [★{r['total_score']}], {source}")
            lines.append(f"[阅读原文 →]({url})")
            if summary:
                lines.append(f"> 🔶 **中文总结**: {summary}\n")
            lines.append("")

    # 8. Write recommend/{DATE}.md
    recommend_dir = os.path.expanduser("~/music-record/recommend")
    os.makedirs(recommend_dir, exist_ok=True)
    md_path = os.path.join(recommend_dir, f"{date_str}.md")
    with open(md_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {md_path}")

    # 9. Print summary for kanban_complete (stdout is captured)
    print(f"\nSUMMARY: aggregated {len(reviews)} unique reviews, {len(passed)} passed filter, recommend written to recommend/{date_str}.md")


if __name__ == "__main__":
    main()