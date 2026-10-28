#!/usr/bin/env python3
"""
scrape_songlines.py — Scrape Songlines reviews (songlines.co.uk).

2026-10-27 重写：站点改版后旧解析路径全线失效（详见下方「为什么重写」）。
新站结构（Umbraco + Tailwind）：
  - 列表页  https://www.songlines.co.uk/reviews-all?getAllReviews=true
    分页     ?getAllReviews=true&itemsPerPage=12&page=N
    卡片     <div aria-label="Article: <专辑名>">
             ├─ h4                        专辑名
             ├─ a[href*=/reviews/musicians/]  艺人
             ├─ p.article__intro           列表页摘要
             ├─ span.font-bold + "/ 10"     站点评分（数字）
             ├─ a[href*=/reviews/reviewers/]  乐评人
             ├─ a[href*=/reviews/regions/]   版块
             └─ p.text-[9px]               期刊月份（"October 2026"）
  - 详情页  https://www.songlines.co.uk/review/<slug>
    正文    单个长 <p>（标 paywall，但正文目前仍可见）

为什么重写（旧路径为什么产出 0 条）：
  - 旧 LIST_URL https://songlines.co.uk/reviews → 现在 404（真实路径是 /reviews-all）
  - 旧卡片选择器 div.review-item / h2 / span.rating / span.small.pt-2 全部消失
  - 旧评分是 ★ 字符计数，新站直接给数字
  - 旧日期串是 "in issue: 10/2026"，新站是 "October 2026"

日期粒度仍是「期刊月份」，窗口沿用旧的 ±45 天（月初对齐），
所以本月刊 + 相邻两期的评论都会进来（与 2026-06 之前每天 ~40 条的产出量级一致）。
"""
import concurrent.futures
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

SITE_ID = "songlines"
SOURCE = "Songlines"
BASE_URL = "https://www.songlines.co.uk"
LIST_URL = f"{BASE_URL}/reviews-all?getAllReviews=true"
PAGE_SIZE = 12
MAX_PAGES = 20
# 期刊月份 → 日期。允许窗口 ±45 天（月初对齐），与旧实现同语义。
WINDOW_DAYS = 45

USER_AGENT = ("Mozilla/5.0 (compatible; music-daily-recs/1.0; "
              "+https://github.com/pty819/music-record)")

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Scrape Songlines reviews")
    p.add_argument("--days", type=float, default=1.5, help="Days back from reference date")
    p.add_argument("--date", help="Reference date YYYY-MM-DD (default: today)")
    return p.parse_args()


def fetch(url: str) -> str:
    """Fetch a URL with curl, return HTML text."""
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "25", "-A", USER_AGENT, url],
        capture_output=True,
        text=True,
        timeout=35,
    )
    if result.returncode != 0:
        sys.stderr.write(f"curl error {result.returncode} for {url}: {result.stderr[:200]}\n")
        return ""
    return result.stdout


def parse_issue_date(text: str):
    """Parse 'October 2026' → (date, iso). Month-level granularity."""
    text = (text or "").strip()
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", text)
    if not m:
        return None, ""
    month = MONTHS.get(m.group(1).lower())
    if not month:
        return None, ""
    try:
        d = datetime(int(m.group(2)), month, 1).date()
    except ValueError:
        return None, ""
    return d, d.isoformat()


def is_recent(issue_date, cutoff) -> bool:
    """±WINDOW_DAYS around cutoff, month-level (issue dates are month starts)."""
    if issue_date is None:
        return False
    allowed_start = cutoff - timedelta(days=WINDOW_DAYS)
    allowed_end = cutoff + timedelta(days=WINDOW_DAYS)
    return allowed_start <= issue_date <= allowed_end


def fetch_article_body(article_url: str):
    """Fetch article page, return (body, excerpt). Body = the long review paragraph."""
    try:
        html = fetch(article_url)
    except Exception:
        return "", ""
    if not html:
        return "", ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    long_paras = [p for p in paras if len(p) > 200]
    body = re.sub(r"\s+", " ", " ".join(long_paras)).strip()
    excerpt = body[:500]
    return body, excerpt


def parse_cards(page_html: str):
    """Parse one listing page into a list of card dicts (no body fetch yet)."""
    soup = BeautifulSoup(page_html, "lxml")
    cards = soup.find_all("div", attrs={"aria-label": re.compile(r"^Article: ")})
    out = []
    for card in cards:
        title_el = card.find("h4")
        link = card.find("a", href=re.compile(r"/review/"))
        if not title_el or not link:
            continue
        url = link["href"]
        if url.startswith("/"):
            url = BASE_URL + url
        album = title_el.get_text(" ", strip=True)

        artist = ""
        musician_link = card.find("a", href=re.compile(r"/reviews/musicians/"))
        if musician_link:
            artist = musician_link.get_text(" ", strip=True)

        # 站点评分：<span class="... text-lg font-bold ...">9</span> 紧邻 "/ 10"
        score = 0
        for span in card.find_all("span"):
            txt = span.get_text(strip=True)
            if txt.isdigit() and 0 <= int(txt) <= 10:
                nxt = span.find_next_sibling("span")
                if nxt and "/ 10" in nxt.get_text(strip=True):
                    score = int(txt)
                    break

        excerpt = ""
        intro = card.find("p", class_=re.compile(r"article__intro"))
        if intro:
            excerpt = intro.get_text(" ", strip=True)

        issue_text = ""
        for p in card.find_all("p", class_=re.compile(r"text-\[9px\]")):
            issue_text = p.get_text(" ", strip=True)
            break
        issue_date, pub_date = parse_issue_date(issue_text)

        out.append({
            "album": album,
            "artist": artist,
            "score": score,
            "url": url,
            "issue_date": issue_date,
            "pub_date": pub_date,
            "excerpt": excerpt[:500],
        })
    return out


def main():
    args = parse_args()
    ref_date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                if args.date else datetime.now(timezone.utc).date())
    cutoff = ref_date - timedelta(days=args.days)

    sys.stderr.write(f"Songlines scraper — Ref date: {ref_date}, Cutoff: {cutoff}\n")

    candidates = []
    seen_urls = set()
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else f"{LIST_URL}&itemsPerPage={PAGE_SIZE}&page={page}"
        html = fetch(url)
        if not html.strip():
            sys.stderr.write(f"  Page {page}: empty response, stop\n")
            break
        cards = parse_cards(html)
        if not cards:
            sys.stderr.write(f"  Page {page}: 0 cards, stop\n")
            break
        in_window = [c for c in cards if is_recent(c["issue_date"], cutoff)]
        sys.stderr.write(f"  Page {page}: {len(cards)} cards, {len(in_window)} in window\n")
        for c in in_window:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                candidates.append(c)
        # 整页都超出窗口 → 更早的页只会更旧，停
        if not in_window and all(c["issue_date"] is None or c["issue_date"] < cutoff for c in cards):
            break
        time.sleep(0.8)

    sys.stderr.write(f"  Fetching {len(candidates)} article bodies...\n")

    def work(card):
        body, excerpt = fetch_article_body(card["url"])
        card["body"] = body
        if not body and card.get("excerpt"):
            excerpt = card["excerpt"]
        card["final_excerpt"] = excerpt[:500]
        return card

    if candidates:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, candidates))

    items = []
    for c in candidates:
        items.append({
            "album": c["album"],
            "artist": c.get("artist") or "",
            "score": c["score"],
            "url": c["url"],
            "source": SOURCE,
            "pub_date": c["pub_date"],
            "tags": "world music",
            "excerpt": c.get("final_excerpt") or c.get("excerpt") or "",
            "body": c.get("body") or "",
            "site_id": SITE_ID,
            "crawl_status": "success",
            "type": "review",
        })

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff.isoformat(),
        },
        "items": items,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.stderr.write(f"Songlines: {len(items)} items (cutoff={cutoff})\n")


if __name__ == "__main__":
    main()
