#!/usr/bin/env python3
"""
fast-rss-scrape.py — 并发抓取所有 RSS 站，输出统一 JSON。

用法:
  python3 fast-rss-scrape.py -o rss_merged.json
  python3 fast-rss-scrape.py --days 3 --workers 16
"""

import argparse
import feedparser
import json
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

socket.setdefaulttimeout(30)

SITES_JSON = Path(__file__).resolve().parent.parent / "data" / "sites.json"
DEFAULT_DAYS = 1.5

TAG_MAP = {
    "the_wire": "experimental avant-garde sound art improvisation",
    "the_quietus": "experimental electronic jazz world psych prog",
    "a_closer_listen": "experimental ambient drone field recording",
    "avant_music_news": "experimental weird progressive avant-garde",
    "bandcamp_daily": "experimental electronic world ambient",
    "igloo_magazine": "experimental electronic IDM ambient glitch",
    "icareifyoulisten": "contemporary classical new music",
    "jazztimes": "jazz",
    "sequenza21": "contemporary classical new music",
    "van_magazine": "classical contemporary",
    "rhythm_passport": "world music folk",
    "progarchives": "progressive rock",
    "rest_is_noise_ph": "asian experimental alternative",
    "attn_magazine": "experimental sound art",
    "chain_dlk": "industrial dark ambient glitch avant-garde",
    "hhv_mag": "electronic vinyl culture electroacoustic",
    "new_music_buff": "contemporary electroacoustic",
    "jazz_journal": "jazz",
    "five_against_four": "modern classical electronic experimental",
    "modern_classical_music": "modern classical contemporary",
    "the_classic_review": "classical contemporary",
    "froots": "folk roots world music",
    "prog_mistress": "prog jazz-rock fusion",
    "side_line": "industrial darkwave EBM electro post-punk",
    "post_punk_com": "post-punk goth darkwave industrial synth",
    "i_die_you_die": "industrial EBM goth dark electro post-punk",
    "peek_a_boo_magazine": "alternative underground gothic industrial darkwave",
    "noise_not_music": "experimental avant-garde noise",
    "the_noise_beneath_the_snow": "noise gothic industrial metal dark ambient neofolk",
    "can_this_even_be_called_music": "experimental underground avant-garde",
    "the_elite_extremophile": "progressive experimental avant-garde",
    "heavy_blog_is_heavy": "progressive experimental avant-garde metal noise",
    "record_crates_united": "experimental underground cult",
    "fluid_radio": "electronic ambient experimental",
    "arban": "jazz free improvisation international culture",
    "hosoda_note": "free improvisation avant-garde sound art japanese experimental",
    "hiroyasu_tangerine": "record review experimental avant-garde improvisation",
    "ontomo": "classical contemporary music jazz improvisation world music",
    "freude": "contemporary classical new music post-classical improvisation",
    "mercure_des_arts": "classical contemporary music improvisation",
    "cinra": "culture music art improvisation",
    "artscape": "art sound art contemporary music improvisation",
    "varelser": "japanese experimental noise improvisation avant-garde",
    "noisenotmusic": "experimental noise improvisation reviews",
    "ajazznoise": "free jazz japanese improvisation noise experimental",
    "kansai_studies": "kansai noise experimental live japanese",
    "prtcll": "experimental underground cassette indie label",
    "komekyo510": "experimental avant-garde noise reviews",
    "leap250": "japanese music indie alternative monthly roundup",
}


def load_sites():
    with open(SITES_JSON) as f:
        data = json.load(f)
    return [s for s in data["sites"] if s.get("has_rss") and s.get("rss_url")]


def _pick_from_archive(num=3):
    """fluid_radio 特殊路径：调用 pick_fluid_radio_archive.py 子进程随机抽 N 条。

    返回 [(site_id, items)] 格式与正常 RSS 抓取一致。
    """
    script_dir = Path(__file__).resolve().parent
    picker = script_dir / "pick_fluid_radio_archive.py"
    try:
        proc = subprocess.run(
            ["python3", str(picker), "-n", str(num)],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            print(f"  [fluid_radio] pick 失败: {proc.stderr.strip()[:200]}", file=sys.stderr)
            return []
        data = json.loads(proc.stdout)
        return data.get("items", [])
    except Exception as e:
        print(f"  [fluid_radio] pick 异常: {e}", file=sys.stderr)
        return []


def parse_rss_date(entry):
    from time import mktime
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed)).date()
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed)).date()
    return None


def get_body(entry):
    body = ""
    if hasattr(entry, "content") and entry.content:
        body = entry.content[0].value if entry.content[0].value else ""
    if not body and hasattr(entry, "summary"):
        body = entry.summary
    if not body and hasattr(entry, "description"):
        body = entry.description
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    body = body.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    body = body.replace("&quot;", '"').replace("&#39;", "'").replace("&#8230;", "…")
    return body


def parse_artist_album(title):
    for sep in [" — ", " – ", " - "]:
        parts = title.split(sep, 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    return "", title


def scrape_site(site, cutoff_date):
    site_id = site["id"]
    name = site["name"]
    rss_url = site["rss_url"]

    # 特殊站点：fluid_radio 走 archive 随机抽取（根 feed 已被博彩污染）
    # 见 references/2026-08-15-fluid-radio-archive-pick.md
    if site_id == "fluid_radio":
        return site_id, _pick_from_archive(num=3)

    feed = feedparser.parse(rss_url)
    entries = feed.entries if hasattr(feed, "entries") else []
    if not entries:
        print(f"  [{site_id}] 0 条", file=sys.stderr)
        return site_id, []

    tags = TAG_MAP.get(site_id, "")
    items = []
    for entry in entries:
        pub_date = parse_rss_date(entry)
        if pub_date is None or pub_date < cutoff_date:
            continue
        title = entry.get("title", "").strip()
        artist, album = parse_artist_album(title)
        body = get_body(entry)
        items.append({
            "album": album,
            "artist": artist,
            "score": None,
            "url": entry.get("link", ""),
            "source": name,
            "pub_date": pub_date.isoformat(),
            "tags": tags,
            "excerpt": body[:500],
            "body": body,
            "site_id": site_id,
            "crawl_status": "success",
            "type": "review",
        })

    print(f"  [{site_id}] {len(items)} 条", file=sys.stderr)
    return site_id, items


def main():
    parser = argparse.ArgumentParser(description="RSS 并发抓取 → 统一 JSON")
    parser.add_argument("-o", "--output", help="输出 JSON 文件（缺省 stdout）")
    parser.add_argument("--days", type=float, default=DEFAULT_DAYS)
    parser.add_argument("--date", help="基准日期 YYYY-MM-DD（缺省今天）")
    parser.add_argument("--workers", type=int, default=8,
                        help="并发线程数（default 8，VPN 下不宜太高）")
    args = parser.parse_args()

    ref_date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                if args.date else datetime.now(timezone.utc).date())
    cutoff_date = ref_date - timedelta(days=args.days)

    sites = load_sites()
    print(f"RSS: {len(sites)} 站, {args.workers} 线程, cutoff ≥ {cutoff_date}",
          file=sys.stderr)

    all_items = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(scrape_site, s, cutoff_date): s["id"]
                   for s in sites}
        for future in as_completed(futures):
            try:
                _site_id, items = future.result()
                all_items.extend(items)
            except Exception as e:
                print(f"  [{futures[future]}] 💥 {e}", file=sys.stderr)

    all_items.sort(key=lambda r: r["pub_date"], reverse=True)

    result = {
        "meta": {
            "total": len(all_items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff_date.isoformat(),
        },
        "items": all_items,
    }

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"\n✅ {len(all_items)} 条 → {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
