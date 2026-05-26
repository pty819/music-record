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
import re
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
API_KEY = os.environ.get("MINIMAX_CN_API_KEY", "")
if not API_KEY:
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip().startswith("MINIMAX_CN_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip().strip("'\"")
                break

BASE_URL = "https://api.minimaxi.com/anthropic"
MODEL = "MiniMax-M2.7"
MAX_TOKENS = 30000
TIMEOUT = 120  # 单次调用超时（秒）
RETRIES = 3

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

{"total_score": <整数 1-10>, "cn_summary": "<150-300 字中文综述>"}

"cn_summary" 要求：
- 150-300 字
- 客观描述音乐风格、亮点和定位
- 不要用"令人惊叹""必听""不容错过"等主观评价词
- 不要包含评分细则的讨论
- 纯中文，不含英文

## 评分示例
- 高质量实验爵士+电子融合，欧洲小众厂牌 → {"total_score": 8, "cn_summary": "实验爵士与电子声响的深度融合，即兴与编程的边界在此消融"}
- 有趣但不够创新的独立摇滚 → {"total_score": 5, "cn_summary": "独立摇滚的扎实之作，编曲工整但缺乏突破性实验元素"}
- 标准商业流行制作 → {"total_score": 3, "cn_summary": "商业流行制作，偏向主流听众，与实验/前卫路线距离较大"}
- 先锋暗潮+工业电子，极具原创性 → {"total_score": 9, "cn_summary": "暗潮与工业电子的前卫融合，声响设计极具侵略性与独创性"}
- 信息不足或纯新闻稿 → {"total_score": 1, "cn_summary": "内容信息不足，无法评估"}
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
    """Call MiniMax API and return parsed (score, summary). Returns (None, None) on failure."""
    client = anthropic.Anthropic(
        api_key=API_KEY,
        base_url=BASE_URL,
        timeout=TIMEOUT,
    )

    for attempt in range(RETRIES):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt_text}],
            )

            # Extract text, skipping ThinkingBlock
            text = ""
            for block in message.content:
                if hasattr(block, "type") and block.type == "text" and hasattr(block, "text"):
                    text = block.text
                    break

            if not text:
                print(f"    [warning] empty response (attempt {attempt + 1})", file=sys.stderr)
                continue

            # Parse JSON from response
            result = None
            # Strategy 1: direct JSON parse
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                pass

            # Strategy 2: extract from markdown code block
            if result is None:
                m = re.search(r'```(?:json)?\s*\n?({.*?})\n?\s*```', text, re.DOTALL)
                if m:
                    try:
                        result = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        pass

            # Strategy 3: find {...} with total_score
            if result is None:
                m = re.search(r'({[^{}]*"total_score"\s*:\s*\d+[^{}]*})', text, re.DOTALL)
                if m:
                    try:
                        result = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        pass

            if result is None:
                print(f"    [warning] cannot parse JSON from response (attempt {attempt + 1})", file=sys.stderr)
                print(f"    response[:200]: {text[:200]}", file=sys.stderr)
                continue

            score = int(result.get("total_score", 0))
            summary = (result.get("cn_summary") or "").strip()

            score = max(1, min(10, score))

            return score, summary

        except Exception as e:
            if attempt < RETRIES - 1:
                delay = 2 ** attempt
                print(f"    [retry {attempt + 1}/{RETRIES}] {e}, waiting {delay}s...", file=sys.stderr)
                time.sleep(delay)
                continue
            print(f"    [fail after {RETRIES} retries] {e}", file=sys.stderr)
            return None, None

    return None, None


def process_single(item):
    """Process one review item: call API, parse result, update item in-place."""
    album = item.get("album", "?")[:50]
    prompt_text = build_prompt(item)
    score, summary = call_minimax(prompt_text)

    if score is not None:
        item["total_score"] = score
        item["_cn_summary"] = summary
        return {"status": "ok", "album": album, "score": score}
    else:
        item["total_score"] = 0
        item["_cn_summary"] = "（评分失败）"
        return {"status": "fail", "album": album}


def main():
    parser = argparse.ArgumentParser(
        description="并发 MiniMax 评分 + 中文总结，读取 scraped_raw.json → 输出 processed.json"
    )
    parser.add_argument("--date-dir", required=True, help="数据目录（如 2026/05/2026-05-27）")
    parser.add_argument("-i", "--input", default="scraped_raw.json", help="输入文件名（默认 scraped_raw.json）")
    parser.add_argument("-o", "--output", default="processed.json", help="输出文件名（默认 processed.json）")
    parser.add_argument("--max-workers", type=int, default=5, help="并发线程数（默认 5）")
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

    # Build output
    success_count = sum(1 for r in results if r.get("status") == "ok")
    fail_count = sum(1 for r in results if r.get("status") != "ok")

    output = {
        "meta": {
            "total": total,
            "success": success_count,
            "failed": fail_count,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "input_file": args.input,
        },
        "items": items,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(file=sys.stderr)
    print(f"✅ {success_count}/{total} 条成功 → {output_path}", file=sys.stderr)
    if fail_count > 0:
        print(f"⚠️ {fail_count} 条失败", file=sys.stderr)

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


if __name__ == "__main__":
    main()
