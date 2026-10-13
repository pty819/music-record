#!/usr/bin/env python3
"""
scrape_roots_world.py — Two-phase RootsWorld scraper.
Phase 1: Camoufox to fetch listing page (bypasses Cloudflare).
Phase 2: curl for each article page (lightweight).
"""
import json, re, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from camoufox import Camoufox

SITE_ID = "roots_world"
SOURCE = "RootsWorld"
BASE = "https://rootsworld.com"
LIST_URL = f"{BASE}/rw/"
CUTOFF_HOURS = 36

NON_MUSIC_RE = re.compile(r"\((?:BLU-RAY|BLU-RAY REVIEW|UHD|VOD|DVD)\)", re.I)
REVIEWER_LINE_RE = re.compile(
    r"^(?:Reviewed\s+by|Review\s+by|By|Interview\s+and\s+review\s+by|"
    r"Recordings\s+and\s+Commentary\s+by|Commentary\s+by)\s+(.+)$", re.I,
)


def curl_fetch(url: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            ["curl", "-sL", "-A", "Mozilla/5.0 (X11; Linux aarch64; rv:128.0) Gecko/20100101 Firefox/128.0",
             "-m", str(timeout), url],
            capture_output=True, timeout=timeout + 5,
        )
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""
    except Exception as e:
        sys.stderr.write(f"curl error {url}: {e}\n")
        return ""


def parse_listing(html: str) -> list:
    """Extract article URLs and metadata from listing page."""
    soup = BeautifulSoup(html, "lxml")
    articles = soup.find_all("article", class_="review-card")
    out = []
    for art in articles:
        more = art.find("a", class_="read-more", href=True)
        href = more.get("href", "") if more else ""
        list_title = more.get_text(" ", strip=True) if more else ""
        if not list_title:
            b = art.find("b")
            if b:
                list_title = b.get_text(" ", strip=True)

        has_mixcloud = bool(art.find("iframe", src=re.compile(r"mixcloud\.com", re.I)))
        has_review_link = bool(art.find("a", class_="read-more", href=re.compile(r"reviews/|interview/")))
        is_podcast = has_mixcloud and not has_review_link
        is_interview = isinstance(href, str) and "/interview/" in href

        if is_podcast:
            pod_idx = sum(1 for x in out if x.get("is_podcast"))
            url = f"{LIST_URL}#podcast-{pod_idx+1}"
        else:
            if isinstance(href, str):
                if href.startswith("//"):
                    url = "https:" + href
                elif href.startswith("/"):
                    url = f"{BASE}{href}"
                elif href.startswith("http"):
                    url = href
                else:
                    url = urljoin(LIST_URL, href)
            else:
                continue

        if not url:
            continue
        out.append({
            "url": url,
            "list_title": list_title or "",
            "is_podcast": is_podcast,
            "is_interview": is_interview,
            "raw_html": str(art),
        })
    return out


def parse_article(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    artist = album = label = reviewer = ""

    hdr = soup.find("div", class_="review-header")
    if hdr:
        p_lines = []
        for child in hdr.children:
            if getattr(child, "name", None) in (None, "img"):
                continue
            if child.name in ("p", "div", "span", "i", "b"):
                t = re.sub(r"\s+", " ", child.get_text(" ", strip=True)).strip()
                if t:
                    p_lines.append(t)
        rev_line = next((ln for ln in p_lines if REVIEWER_LINE_RE.match(ln)), None)
        photo_line = next((ln for ln in p_lines if re.match(r"^Photos?:", ln, re.I)), None)
        if rev_line:
            m = REVIEWER_LINE_RE.match(rev_line)
            if m:
                reviewer = m.group(1).strip()
        fields = [ln for ln in p_lines if ln not in (rev_line or "") and ln != (photo_line or "")]
        if len(fields) >= 1:
            artist = fields[0]
        if len(fields) >= 2:
            album = fields[1]
        if len(fields) >= 3:
            label = fields[2]

    body_div = soup.find("div", class_="review-body")
    body_text = ""
    if body_div:
        body_text = body_div.get_text("\n", strip=True)
    else:
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = soup.find("body").get_text("\n", strip=True) if soup.find("body") else ""

    # Plain-text reviewer fallback
    if not reviewer:
        lines = [ln.strip() for ln in body_text.splitlines() if ln.strip()]
        for ln in lines[:6]:
            m = REVIEWER_LINE_RE.match(ln)
            if m:
                reviewer = m.group(1).strip()
                break

    return {"title": title, "artist": artist, "album": album, "label": label,
            "reviewer": reviewer, "body": body_text}


def main():
    ref_date = datetime.now(timezone.utc)
    cutoff = ref_date - timedelta(hours=CUTOFF_HOURS)
    out_path = "/home/liyifan/music-record/2026/06/2026-06-10/roots_world_reviews.json"
    sys.stderr.write(f"[roots_world] ref={ref_date.date()}, cutoff={cutoff.isoformat()}\n")

    # Phase 1: Get listing page via Camoufox
    sys.stderr.write("[roots_world] Phase 1: Fetching listing via Camoufox...\n")
    try:
        with Camoufox(headless=True, humanize=True) as b:
            ctx = b.new_context()
            page = ctx.new_page()
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
            # Check for cookie button
            try:
                accept = page.query_selector("button:has-text('Accept'), button:has-text('I Agree')")
                if accept:
                    accept.click()
                    time.sleep(1)
                    sys.stderr.write("[roots_world] Accepted cookie\n")
            except Exception:
                pass
            html = page.content()
        sys.stderr.write(f"[roots_world] Listing page fetched ({len(html)} bytes)\n")
    except Exception as e:
        sys.stderr.write(f"[roots_world] FATAL: Camoufox failed: {e}\n")
        result = {"meta": {"total": 0, "scraped_at": datetime.now(timezone.utc).isoformat(),
                           "cutoff_date": cutoff.isoformat(), "site": SITE_ID, "error": str(e)}, "items": []}
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    articles = parse_listing(html)
    sys.stderr.write(f"[roots_world] Phase 2: {len(articles)} articles found\n")

    items = []
    seen = set()
    for n, li in enumerate(articles):
        url = li["url"]
        if url in seen:
            continue
        seen.add(url)

        if NON_MUSIC_RE.search(li["list_title"]):
            sys.stderr.write(f"  skip non-music: {url}\n")
            continue

        if li["is_podcast"]:
            parsed = parse_article(li["raw_html"])
            parsed["title"] = li["list_title"]
            parsed["album"] = li["list_title"]
            parsed["artist"] = "RootsWorld Radio"
            body_parts = [p.get_text(" ", strip=True) for p in
                          BeautifulSoup(li["raw_html"], "lxml").find_all("p") if p.get_text(" ", strip=True)]
            parsed["body"] = "\n".join(body_parts)
            item_type = "tracklist"
            album = li["list_title"]
            artist = "RootsWorld Radio"
            body_out = parsed["body"]
        else:
            sys.stderr.write(f"  [{n+1}/{len(articles)}] {url}\n")
            art_html = curl_fetch(url)
            if not art_html:
                sys.stderr.write(f"  fetch failed: {url}\n")
                continue
            parsed = parse_article(art_html)
            title = parsed.get("title", "") or ""
            body = parsed.get("body", "") or ""
            if NON_MUSIC_RE.search(body + " " + title):
                sys.stderr.write(f"  skip non-music body: {url}\n")
                continue
            album = parsed["album"] or ""
            artist = parsed["artist"] or ""
            item_type = "review"
            if li["is_interview"]:
                item_type = "feature"
            elif not album:
                if "interview" in (body + " " + title).lower()[:400]:
                    item_type = "feature"
            if not album and not artist:
                album = title
            body_out = body

        # Clean body footer
        body_out = re.split(
            r"Search\s+RootsWorld|Subscribe\s+and\s+Support|Find\s+\w[\w\s]+\s+online\.?$",
            body_out, maxsplit=1
        )[0].strip()
        body_out = re.sub(
            r"^(?:Review(?:ed)?\s+by|By|Commentary\s+by|Recordings\s+and\s+Commentary\s+by)\s+[^\n]+\n+",
            "", body_out, flags=re.I,
        ).strip()

        item = {
            "album": album,
            "artist": artist,
            "score": None,
            "url": url,
            "source": SOURCE,
            "pub_date": "",
            "tags": "world music",
            "excerpt": body_out[:500] if body_out else "",
            "body": body_out,
            "site_id": SITE_ID,
            "crawl_status": "ok",
            "type": item_type,
        }
        if parsed.get("label"):
            item["label"] = parsed["label"]
        if parsed.get("reviewer"):
            item["reviewer"] = parsed["reviewer"]
        items.append(item)

    result = {
        "meta": {
            "total": len(items),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff.isoformat(),
            "site": SITE_ID,
            "pages_crawled": 1,
            "articles_listed": len(articles),
        },
        "items": items,
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    sys.stderr.write(f"[roots_world] Done: {len(items)} items → {out_path}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
