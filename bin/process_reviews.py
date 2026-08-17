#!/usr/bin/env python3
"""
process_reviews.py — 并发调 MiniMax 评分 + 中文总结。

读取 scraped_raw.json，线程池并发调用 MiniMax API，
每条约 15-20 秒（并发 N 条约等于 1 条的时间），写入 processed.json。

用法:
  cd /home/liyifan/music-record
  python3 bin/process_reviews.py --date-dir 2026/05/2026-05-27
  python3 bin/process_reviews.py --date-dir 2026/05/2026-05-27 --max-workers 3 -o processed.json

环境变量: MINIMAX_CN_API_KEY（缺省从 ~/.hermes/.env 读取）
"""
import argparse
import concurrent.futures
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("❌ 需要 anthropic 库：pip install anthropic", file=sys.stderr)
    sys.exit(1)

# ── 配置 ────────────────────────────────────────────────
# 评分模型改为多 provider 容错：MiniMax-M3 主，火山 Ark DeepSeek 备。
# 单点配额耗尽（429/2056）自动切换，保证每日推荐不中断。
from provider_failover import call_with_failover, get_stats, get_switch_log, PROVIDERS

# 主 provider 显示名（供日志）
MODEL = PROVIDERS[0]["model"]
BASE_URL = PROVIDERS[0]["base_url"]

# ── 评分细则（注入 API prompt） ─────────────────────────

SCORING_RUBRIC = """## 用户口味背景
该用户主要关注以下音乐类型（按偏好排序）：
- 实验/前卫音乐（experimental, avant-garde, progressive）
- 学院派爵士（academic jazz, free jazz, improvisation）
- 电子音乐（electronic, IDM, ambient, glitch）
- 世界音乐（world, folk, global fusion）
- 暗潮（darkwave, dark ambient, industrial, goth, EBM, post-punk）
- 当代古典/现代作曲（contemporary classical, modern composition）

## 评分细则（总分 1-10 分，整数）

1. **口味匹配度（权重最高）**：
   - 实验/前卫/爵士/电子/世界/暗潮 → 高分（7-10）
   - 接近上述口味的跨界融合 → 中高分（5-7）
   - 主流流行/商业摇滚/纯古典（非当代）/纯民谣（非世界）→ 低分（1-4）

2. **创新性和独特性**：
   - 独特的艺术视角、创新的声音设计、实验性元素 → 加分
   - 模式化的类型作品、缺乏个人特色 → 减分

3. **跨领域融合**：
   - 融合多种音乐类型（如爵士+电子、世界音乐+实验、暗潮+古典）→ 加分
   - 单一类型内的常规作品 → 不加分也不减分

4. **地区特色加分**：
   - 来自非主流音乐地区（东南亚、东欧、非洲、拉丁美洲、中东）→ +1
   - 带有独特的文化视角或传统乐器融合 → 额外 +1

5. **主流降权**：
   - 大型主流厂牌（Universal/Sony/Warner）、纯商业发行 → -1 到 -2
   - 独立/地下/小众厂牌 → 不加分也不减分

6. **评论质量修正**：
   - 如果原文 excerpt 或 body 内容太短（<200 字符）说明信息不足 → -1
   - 内容为转载/纯新闻稿（非原创乐评）→ -1

## 输出格式

你必须输出**严格有效的 JSON 对象**，不要包含其他文字、注释或 markdown 代码块标记。必须使用以下 JSON 格式：

{"total_score": <整数 1-10>, "genre": "<英文音乐风格，3-6个词，用 / 分隔>", "cn_summary": "<150-300 字中文综述>"}

### genre 字段要求
- 用英文提取文章中描述的音乐风格/类型
- 3-6 个风格词，用 " / " 分隔
- 按主要到次要排序
- 示例: "free jazz / improvisation / avant-garde", "ambient / field recording / drone", "post-punk / darkwave / shoegaze"

### cn_summary 字段要求
- 150-300 字
- 专注描述乐评内容：这张专辑做了什么、怎么做的、为什么值得听
- 不要重复 genre 已经表达的风格信息
- 不要用"令人惊叹""必听""不容错过"等主观评价词
- 不要包含评分细则的讨论
- 纯中文，不含英文

## 评分示例
- 高质量实验爵士+电子融合，欧洲小众厂牌 → {"total_score": 8, "genre": "experimental jazz / electronic / fusion", "cn_summary": "即兴与编程的边界在此消融，萨克斯与合成器形成对话"}
- 有趣但不够创新的独立摇滚 → {"total_score": 5, "genre": "indie rock / alternative", "cn_summary": "编曲工整但缺乏突破性实验元素，吉他音墙扎实"}
- 标准商业流行制作 → {"total_score": 3, "genre": "pop / mainstream", "cn_summary": "商业流行制作，偏向主流听众，与实验路线距离较大"}
- 先锋暗潮+工业电子 → {"total_score": 9, "genre": "darkwave / industrial / electronic", "cn_summary": "声响设计极具侵略性与独创性，合成器层叠构建压迫感"}
- 信息不足或纯新闻稿 → {"total_score": 1, "genre": "unknown", "cn_summary": "内容信息不足，无法评估"}
"""


def build_prompt(item):
    """Build the full prompt for one review item."""
    album = item.get("album", "未知专辑")
    artist = item.get("artist", "")
    source = item.get("source", "未知来源")

    # Prefer body (full text), fall back to excerpt
    excerpt = (item.get("body") or item.get("excerpt") or "")
    # Truncate to avoid token overflow
    excerpt = excerpt[:3000]

    artist_str = f" — {artist}" if artist else ""

    prompt = f"""请根据以下乐评内容进行评分和总结。

## 文章内容
**专辑**: {album}{artist_str}
**来源**: {source}

**正文**:
{excerpt}

{SCORING_RUBRIC}"""
    return prompt


def call_minimax(prompt_text):
    """带多 provider 容错的评分调用（MiniMax 主 → 火山 Ark 备）。

    返回 (score, genre, summary) 三元组，全失败返回 (None, None, None)。
    实际容错逻辑在 provider_failover.call_with_failover，这里保留函数名
    以便 process_single 无感调用。切换记录在 get_switch_log()。
    """
    score, genre, summary, provider = call_with_failover(prompt_text)
    if provider == "ark" and score is not None:
        print(f"    ⚡ 本条由 {provider} 评分", file=sys.stderr)
    return score, genre, summary


def is_non_review_content(item):
    """Detect 商品页 / 博彩推广 / 站外广告 等非乐评内容，提前过滤。

    触发条件：body/excerpt 含多个强特征词同时命中，置信度高。
    命中后直接打 0 分，不浪费 MiniMax API 调用。

    当前规则（基于 8-15 数据验证）：
    - triple_bk_product_page: "MP3 Release" + 价格(£X.XX) + "Add to crate" → boomkat 商品页
    - fluid_radio_spam: site_id=fluid_radio + body 含 gamstop/casino/betting → 博彩 SEO 污染
    - generic_spam: body 含 Casinos / Non GamStop / UK Players → 通用赌博推广
    """
    import re as _re
    body = item.get("body") or ""
    excerpt = item.get("excerpt") or ""
    text = (body + "\n" + excerpt).lower()
    site_id = (item.get("site_id") or "").lower()

    # 规则 1: boomkat 商品页（三重命中，95.5% 准确）
    if "mp3 release" in text and _re.search(r"£\d+\.\d{2}", text) and _re.search(r"add to crate", text):
        return "product_page"

    # 规则 2: fluid_radio 博彩污染（站点特化，比规则 3 更严格）
    if site_id == "fluid_radio" and any(k in text for k in ("gamstop", "casino", "betting", "wagering", "gambling")):
        return "spam_fluid_radio"

    # 规则 3: 通用赌博/博彩推广（跨站点）
    spam_signals = ("casinos not on gamstop", "non gamstop casino", "non-gamstop casino",
                    "online gambling platform", "online betting platform")
    if any(s in text for s in spam_signals):
        return "spam_generic"

    return None


def process_single(item):
    """Process one review item: call API, parse result, update item in-place."""
    album = item.get("album", "?")[:50]
    site_id = item.get("site_id", "")

    # 前置过滤：商品页 / 博彩污染 → 直接 0 分，跳过 API 调用
    filter_reason = is_non_review_content(item)
    if filter_reason:
        item["total_score"] = 0
        item["_genre"] = "unknown"
        item["_cn_summary"] = f"（{filter_reason}，已过滤）"
        item["_filter_reason"] = filter_reason
        return {"status": "filtered", "album": album, "site_id": site_id,
                "reason": filter_reason}

    prompt_text = build_prompt(item)
    score, genre, summary = call_minimax(prompt_text)

    if score is not None:
        item["total_score"] = score
        item["_genre"] = genre
        item["_cn_summary"] = summary
        return {"status": "ok", "album": album, "score": score}
    else:
        item["total_score"] = 0
        item["_genre"] = "unknown"
        item["_cn_summary"] = "（评分失败）"
        return {"status": "fail", "album": album}


def main():
    parser = argparse.ArgumentParser(
        description="并发 MiniMax 评分 + 中文总结，读取 scraped_raw.json → 输出 processed.json"
    )
    parser.add_argument("--date-dir", required=True, help="数据目录（如 2026/05/2026-05-27）")
    parser.add_argument("-i", "--input", default="scraped_raw.json", help="输入文件名（默认 scraped_raw.json）")
    parser.add_argument("-o", "--output", default="processed.json", help="输出文件名（默认 processed.json）")
    parser.add_argument("--max-workers", type=int, default=3, help="并发线程数（默认 3，避免 SBC 过载）")
    args = parser.parse_args()

    # Resolve paths
    if args.date_dir.startswith("/"):
        base_dir = Path(args.date_dir)
    else:
        base_dir = Path.cwd() / args.date_dir

    input_path = base_dir / args.input
    output_path = base_dir / args.output

    if not input_path.exists():
        print(f"❌ 输入文件不存在：{input_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = data.get("items", []) if isinstance(data, dict) else data
    total = len(items)

    if total == 0:
        print("❌ 输入文件没有条目", file=sys.stderr)
        sys.exit(1)

    print(f"📦 {total} 条待处理，并发 {args.max_workers} 线程", file=sys.stderr)
    print(f"   模型: {MODEL}", file=sys.stderr)
    print(f"   端点: {BASE_URL}", file=sys.stderr)
    print(file=sys.stderr)

    results = []
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(process_single, item): i for i, item in enumerate(items)}

        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                r = future.result()
                results.append(r)
            except Exception as e:
                results.append({"status": "error", "index": idx, "error": str(e)})

            completed += 1
            if completed % 5 == 0 or completed == total:
                ok = sum(1 for r in results if r.get("status") == "ok")
                bar = "█" * (ok * 30 // max(completed, 1)) + "░" * (30 - ok * 30 // max(completed, 1))
                print(f"  [{completed}/{total}] {bar} ✅ {ok} ok", file=sys.stderr)

    # Sort by score descending
    items.sort(key=lambda r: r.get("total_score", 0), reverse=True)

    # ── 低分清理：物理删除 <=2 分的条目（用户要求，省空间）──
    # 保留 >=3 分的条目。过滤条目（已打 0 分）与评分失败（0 分）也一并清除。
    LOW_SCORE_CUTOFF = 2
    kept_items = [i for i in items if i.get("total_score", 0) > LOW_SCORE_CUTOFF]
    removed_count = len(items) - len(kept_items)
    if removed_count > 0:
        print(f"🗑 清理 {removed_count} 条 <= {LOW_SCORE_CUTOFF} 分条目（省空间）",
              file=sys.stderr)
    items = kept_items

    # Build output
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    fail_count = sum(1 for r in results if r.get("status") == "fail")
    filtered_count = sum(1 for r in results if r.get("status") == "filtered")
    error_count = sum(1 for r in results if r.get("status") == "error")

    # 失败条目详情（用于可观测性，synthesizer 可选读取生成告警）
    failed_items = [
        {"album": r.get("album", "?"), "site_id": r.get("site_id"),
         "reason": r.get("reason") or r.get("error", "评分失败")}
        for r in results if r.get("status") in ("fail", "error")
    ][:50]  # cap at 50 to keep meta small

    # 过滤条目按 reason 聚合
    filter_breakdown = {}
    for r in results:
        if r.get("status") == "filtered":
            reason = r.get("reason", "unknown")
            filter_breakdown[reason] = filter_breakdown.get(reason, 0) + 1

    output = {
        "meta": {
            "total": total,
            "success": ok_count,
            "failed": fail_count,
            "filtered": filtered_count,
            "errors": error_count,
            "filter_breakdown": filter_breakdown,
            "failed_items": failed_items,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "input_file": args.input,
        },
        "items": items,
    }

    print(file=sys.stderr)
    print(f"✅ {ok_count}/{total} 条成功 → {output_path}", file=sys.stderr)
    if filtered_count > 0:
        bd = ", ".join(f"{k}={v}" for k, v in filter_breakdown.items())
        print(f"🚫 {filtered_count} 条已过滤（{bd}）", file=sys.stderr)
    if fail_count > 0:
        print(f"⚠️ {fail_count} 条评分失败", file=sys.stderr)

    # Print top scores
    scored = [i for i in items if i.get("total_score", 0) > 0]
    scored.sort(key=lambda r: r["total_score"], reverse=True)
    print(f"\n🏆 最高分：", file=sys.stderr)
    for item in scored[:5]:
        album = item.get("album", "?")[:50]
        score = item.get("total_score", 0)
        summary = (item.get("_cn_summary") or "")[:60]
        print(f"   {score}/10  {album}", file=sys.stderr)
        if summary:
            print(f"            {summary}", file=sys.stderr)

    # Provider failover 统计（当天用了哪个 provider / 切换了几次）
    stats = get_stats()
    switch_log = get_switch_log()
    print(f"\n🔌 Provider 统计: {json.dumps(stats)}", file=sys.stderr)
    if switch_log:
        print(f"🔀 切换记录 ({len(switch_log)} 次):", file=sys.stderr)
        for line in switch_log[-10:]:
            print(f"   {line}", file=sys.stderr)
    else:
        print("🔀 无切换（全程主 provider）", file=sys.stderr)
    # 把切换统计写进 meta，报告可追溯
    output["meta"]["provider_stats"] = stats
    output["meta"]["provider_switch_log"] = switch_log
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
