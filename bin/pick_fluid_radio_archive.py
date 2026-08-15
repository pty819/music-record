#!/usr/bin/env python3
"""
pick_fluid_radio_archive.py — 从 fluid_radio_archive.json 随机抽 N 条作为今日 RSS 补充。

工作流程：
  1. 读 data/fluid_radio_archive.json
  2. 过滤：排除 _last_picked_date == 今天（避免同日重复推送）
  3. 随机抽 N 条（默认 3）
  4. 标记 _last_picked_date = 今天，写回存档
  5. 输出与 fast-rss-scrape.py 同构的 JSON（meta + items），stdout 或 -o 文件

设计原则：
  - 抽过的条目标记日期 → 不重复推送（除非所有都抽过，则 reset 最早）
  - 输出走 stdout，可直接 pipe 进 merge_scraped.py
  - 调用方：fast-rss-scrape.py 之后、merge_scraped.py 之前

用法:
  python3 bin/pick_fluid_radio_archive.py -o $DATE_DIR/fluid_radio_picks.json
  python3 bin/pick_fluid_radio_archive.py -n 5   # 抽 5 条
  cat picks.json | python3 bin/merge_scraped.py ...   # pipe
"""
import argparse
import json
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ARCHIVE_FILE = Path(__file__).resolve().parent.parent / "data" / "fluid_radio_archive.json"
SITE_ID = "fluid_radio"
SOURCE = "Fluid Radio"
TODAY = date.today().isoformat()


def load_archive():
    if not ARCHIVE_FILE.exists():
        print(f"❌ 存档不存在: {ARCHIVE_FILE}", file=sys.stderr)
        print("请先运行: python3 bin/fetch_fluid_radio_archive.py", file=sys.stderr)
        sys.exit(1)
    return json.loads(ARCHIVE_FILE.read_text(encoding="utf-8"))


def save_archive(archive):
    ARCHIVE_FILE.write_text(json.dumps(archive, indent=2, ensure_ascii=False), encoding="utf-8")


def pick(archive, n=3, seed=None):
    """Pick n items not picked today; reset earliest if exhausted."""
    items = archive["items"]
    # 可选池：今天没抽过的
    pool = [i for i in items if i.get("_last_picked_date") != TODAY]
    if not pool:
        # 全部抽过了 → reset 最早的 30%（让旧条目重新可抽）
        sys.stderr.write("⚠️  今日可选池已空，reset 最早 30% 标记\n")
        items_sorted = sorted(items, key=lambda x: x.get("_last_picked_date") or "")
        reset_n = max(n * 10, int(len(items) * 0.3))
        for it in items_sorted[:reset_n]:
            it["_last_picked_date"] = None
        pool = items_sorted[:reset_n]

    rng = random.Random(seed) if seed is not None else random.Random()
    chosen = rng.sample(pool, min(n, len(pool)))

    # 标记 + 复制（不修改原 items 的引用，防止 merge 阶段把 _last_picked_date 写回 archive）
    output_items = []
    chosen_urls = set()
    for it in chosen:
        it["_last_picked_date"] = TODAY
        # 深拷贝（去掉内部字段）→ 输出干净 items
        clean = {k: v for k, v in it.items() if not k.startswith("_")}
        output_items.append(clean)
        chosen_urls.add(it["url"])

    return output_items, len(chosen)


def main():
    parser = argparse.ArgumentParser(description="从 fluid_radio_archive 随机抽 N 条")
    parser.add_argument("-n", "--num", type=int, default=3, help="抽几条（默认 3）")
    parser.add_argument("-o", "--output", help="输出文件（缺省 stdout）")
    parser.add_argument("--seed", type=int, help="随机种子（用于可复现测试）")
    args = parser.parse_args()

    archive = load_archive()
    chosen, n_picked = pick(archive, n=args.num, seed=args.seed)

    result = {
        "meta": {
            "total": n_picked,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source": "fluid_radio_archive (random pick)",
            "archive_size": len(archive["items"]),
        },
        "items": chosen,
    }

    # 先回写存档（标记 _last_picked_date）
    save_archive(archive)

    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"✅ {n_picked} 条 → {args.output}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
