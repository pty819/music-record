#!/usr/bin/env python3
"""
scrape_mixmag_asia.py — Chromium-based scraper for Mixmag Asia.

Mixmag Asia is primarily a music news/features site, not a review site.
Captures recent articles from the /music page.

Strategy:
  1. Open a tab on https://mixmag.asia/music via camofox_client.CamofoxClient
  2. Evaluate JS to extract articles (titles, URLs, dates, excerpts)
  3. For each article, navigate to its URL and fetch full body text
  4. Close tabs
  5. Output structured JSON to stdout

Output format:
  {"meta": {"total": N, "scraped_at": "...", "cutoff_date": "..."}, "items": [
    {album, artist, score (None), url, source, pub_date (ISO or ''),
     tags='electronic,asia', excerpt (first 500 of body), body (full),
     site_id='mixmag_asia', crawl_status, type}
  ]}

Usage:
  python3 scrape_mixmag_asia.py [--days 2] [--date YYYY-MM-DD]
"""
import argparse
import json
import sys
import re
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from camofox_client import CamofoxClient, wait_for_content  # noqa: E402

_CHROME = CamofoxClient(user_id="scraper_mixmag_asia", session_key="session_mix", settle=4.0, timeout=120)

# JS to get full body text from an article page
# 2026-10-27: 原来优先取 <article>，实测那只有 211 字符（是侧栏/摘要容器），
# 真正的正文在 <main> 里（4248 字符）。改成按内容长度挑最大的容器。
GET_BODY_JS = """
() => {
    const pick = (el) => el && el.innerText ? el.innerText : '';
    const candidates = [
        pick(document.querySelector('main')),
        pick(document.querySelector('article')),
        pick(document.querySelector('.article-body')),
        pick(document.querySelector('.post-content')),
        pick(document.querySelector('.entry-content')),
        pick(document.body),
    ].filter(t => t && t.length > 200);
    if (!candidates.length) return '';
    return candidates.sort((a, b) => b.length - a.length)[0].slice(0, 10000);
}
"""


def _req(method, path, body=None):
    """驱动本地 Camofox（Camoufox 反检测 Firefox）取数。

    2026-10-27：从 Hermes 自带 Chromium（CDP）换回 Camofox —— 反检测指纹
    对 Cloudflare 站更有效，且 Camofox 已是本机常驻服务。
    """
    if method == "POST" and path.rstrip("/") == "/tabs":
        return _CHROME.open_tab((body or {}).get("url", "about:blank"))
    return _CHROME.call(method, path, body)


def extract_articles(tab_id):
    """Extract article data from the page DOM."""
    js = """(() => {
        const articles = [];
        const sections = document.querySelectorAll('section, div[class*="article"], div[class*="post"], div[class*="card"]');
        const seen = new Set();
        sections.forEach(s => {
            const h = s.querySelector('h2, h3, h4');
            if (!h) return;
            const title = h.textContent.trim();
            if (!title || title.length < 5) return;
            const link = h.querySelector('a');
            const url = link ? link.href : '';
            if (!url || seen.has(url)) return;
            seen.add(url);
            const p = s.querySelector('p');
            const excerpt = p ? p.textContent.trim().slice(0, 500) : '';
            // Try to find a date
            let dateText = '';
            const timeEl = s.querySelector('time');
            if (timeEl) dateText = timeEl.getAttribute('datetime') || timeEl.textContent.trim();
            if (!dateText) {
                const cats = s.querySelectorAll('span, a');
                cats.forEach(c => {
                    const txt = c.textContent.trim();
                    const m = txt.match(/(January|February|March|April|May|June|July|August|September|October|November|December)\\\s+\\\d+,\\\s+\\\d{4}/);
                    if (m) dateText = m[0];
                });
            }
            const catEl = s.querySelector('[class*="category"], [class*="tag"], [class*="section"]');
            const category = catEl ? catEl.textContent.trim() : '';
            articles.push({title, url, excerpt, dateText, category});
        });
        // 导航兜底。/music/ 现在只剩栏目分类页（/music/reviews、/music/premiere…），
        // 只有路径至少三段的才算深层页；真文章在下面的 /feature/ /read/ 分支里取。
        const links = document.querySelectorAll('a[href*="/music/"], a[href*="/features/"]');
        links.forEach(a => {
            const title = a.textContent.trim();
            if (!title || title.length < 5) return;
            const url = a.href;
            // /music/reviews 这类两段路径是栏目导航，不是文章
            try {
                if (new URL(url).pathname.split('/').filter(Boolean).length < 3) return;
            } catch (e) { return; }
            if (seen.has(url)) return;
            seen.add(url);
            articles.push({title, url, excerpt: '', dateText: '', category: ''});
        });
        const realLinks = document.querySelectorAll(
            'a[href*="/feature/"], a[href*="/read/"], a[href*="/news/"]');
        realLinks.forEach(a => {
            // 2026-10-18: a.textContent 会把栏目 tab（"Mixes"/"Features"）和摘要
            // 一起拼进来。链接内固定有一个 h2/h3/h4 标题元素，优先取它，取不到
            // 再退回清洗空白后的 textContent。
            const h = a.querySelector('h1, h2, h3, h4');
            const title = ((h && h.innerText) || (a.textContent || ''))
                .replace(/\s+/g, ' ').trim();
            if (!title || title.length < 5) return;
            const url = a.href;
            if (!url || seen.has(url)) return;
            seen.add(url);
            const p = a.parentElement ? a.parentElement.querySelector('p') : null;
            articles.push({title, url, excerpt: p ? p.textContent.trim().slice(0, 500) : '',
                           dateText: '', category: ''});
        });
        return JSON.stringify(articles);
    })()"""
    resp = _req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js})
    raw = resp.get("result", "[]")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def fetch_body(tab_id, url):
    """Navigate to a URL and fetch full body text."""
    try:
        _req("POST", f"/tabs/{tab_id}/navigate", {"url": url})
        # 2026-10-27: 原为固定 time.sleep(2) 等渲染。Camofox 走真实 Firefox
        # 网络栈，CF 站更慢，固定等待会提前提取 → 正文为空。
        # 改成轮询等正文出现（最长 12s）。
        result = wait_for_content(
            _CHROME, tab_id, GET_BODY_JS, attempts=12, delay=1.0,
        )
        if result is None:
            return ""
        return str(result).strip()[:10000]
    except Exception as e:
        sys.stderr.write(f"  ERROR fetching body for {url}: {e}\n")
        return ""


def parse_date(text):
    """Try to parse a date string into ISO date."""
    if not text:
        return None
    text = text.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Mixmag Asia articles"
    )
    parser.add_argument(
        "--days", type=float, default=1.5,
        help="Max age in days for articles (default: 2)"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Explicit cutoff date (YYYY-MM-DD). Overrides --days."
    )
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    if args.date:
        try:
            cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.stderr.write(f"ERROR: Invalid --date format '{args.date}'. Use YYYY-MM-DD.\n")
            sys.exit(1)
    else:
        cutoff_date = today - timedelta(days=args.days)

    sys.stderr.write(
        f"Mixmag Asia scraper — Today: {today}, Cutoff: {cutoff_date}, "
        f"Days: {args.days}\n"
    )

    # Create tab and navigate to /music page
    tab = _req("POST", "/tabs", {
        "userId": "mixmag", "sessionKey": "mixmag",
        "url": "https://mixmag.asia/music"
    })
    tab_id = tab.get("tabId", "")
    if not tab_id:
        result = {
            "meta": {"total": 0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()},
            "items": []
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    try:
        # 2026-10-27: 原为固定 time.sleep(3) 等页面渲染。Camofox 走真实
        # Firefox 网络栈，CF 站更慢 —— 改成轮询等列表就绪。
        # 注意选择器必须包含 /read/：实测建 tab 后 0s 只有 108 个链接，5s 后
        # 才涨到 112（真文章 /read/... 这时才出现）。只查 /music/ 会永远等不到。
        wait_for_content(
            _CHROME, tab_id,
            "document.querySelectorAll('a[href*=\"/read/\"], a[href*=\"/features/\"], "
            "a[href*=\"/music/\"]').length",
            attempts=15, delay=1.0,
        )
        articles = extract_articles(tab_id)

        items = []
        seen = set()
        total_articles = len(articles)
        for idx, a in enumerate(articles):
            title = a.get("title", "").strip()
            url = a.get("url", "")
            if not title or len(title) < 5 or url in seen:
                continue
            seen.add(url)

            excerpt = a.get("excerpt", "").strip()[:500]
            date_text = a.get("dateText", "")

            pub_date = parse_date(date_text)

            if pub_date and pub_date < cutoff_date:
                continue

            # Skip non-music articles
            cat = a.get("category", "").lower()
            if cat and cat not in ("music", "reviews", "features", "premiere", ""):
                continue

            # Fetch full body by navigating to the article page
            sys.stderr.write(f"  [{idx+1}/{total_articles}] Fetching body: {title[:60]}...\n")
            body = fetch_body(tab_id, url)

            # Determine type
            is_review = any(k in title.lower() for k in ["review:", "album review"])
            article_type = "review" if is_review else "feature"

            # Try to extract artist/album
            artist = ""
            album = title
            for sep in [" – ", " — ", " - "]:
                if sep in title:
                    parts = title.split(sep, 1)
                    artist = parts[0].strip()
                    album = parts[1].strip()
                    break

            items.append({
                "album": album,
                "artist": artist,
                "score": None,
                "url": url,
                "source": "Mixmag Asia",
                "pub_date": pub_date.isoformat() if pub_date else "",
                "tags": "electronic,asia",
                "excerpt": (excerpt or body)[:500],
                "body": body,
                "site_id": "mixmag_asia",
                "crawl_status": "success",
                "type": article_type,
            })

        result = json.dumps({
            "meta": {
                "total": len(items),
                "scraped_at": today.isoformat(),
                "cutoff_date": cutoff_date.isoformat(),
            },
            "items": items
        }, indent=2, ensure_ascii=False)
        print(result)
        sys.stderr.write(f"Mixmag Asia: {len(items)} items\n")
    finally:
        try:
            _req("DELETE", f"/tabs/{tab_id}")
        except:
            pass


if __name__ == "__main__":
    main()
