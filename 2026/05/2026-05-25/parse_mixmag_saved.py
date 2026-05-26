#!/usr/bin/env python3
"""Parse existing saved HTML files into mixmag_asia_reviews.json."""
from pathlib import Path
import json, re
from datetime import datetime, timedelta

WORKSPACE = Path("/home/liyifan/music-record/2026/05/2026-05-25")
OUTPUT = WORKSPACE / "mixmag_asia_reviews.json"
SITE_ID = "mixmag_asia"
SOURCE = "Mixmag Asia"
CUTOFF_DAYS = 3
cutoff = datetime.now() - timedelta(days=CUTOFF_DAYS)
EXCLUDES = ["BLU-RAY", "UHD", "VOD", "DVD"]
EXCLUDE_RE = re.compile("|".join(EXCLUDES), re.IGNORECASE)


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    for fmt in ["%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%d/%m/%Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except Exception:
            pass
    return None


def parse_articles(html):
    records = []
    seen = set()

    blob_pat = re.compile(
        r'<article class="story-block(?: story-block--\w+)* "[^>]*>(.*?)</article>',
        re.DOTALL
    )
    href_pat = re.compile(r'href="(/read/[^"]+)"')
    title_pat = re.compile(r'<h3 class="story-block__title"[^>]*>(.*?)</h3>')
    excerpt_pat = re.compile(
        r'<div class="story-block__excerpt"[^>]*>.*?<p>(.*?)</p>',
        re.DOTALL
    )

    for blob in blob_pat.findall(html):
        href_m = href_pat.search(blob)
        if not href_m:
            continue
        href = href_m.group(1)
        url = f"https://mixmag.asia{href}"
        if url in seen:
            continue
        seen.add(url)

        title_m = title_pat.search(blob)
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

        excerpt_m = excerpt_pat.search(blob)
        excerpt = re.sub(r"<[^>]+>", "", excerpt_m.group(1)).strip() if excerpt_m else ""
        excerpt = excerpt[:500]

        deck_pat = re.compile(
            r'<p[^>]*class="story-block__excerpt"[^>]*>.*?<p>(.*?)</p>',
            re.DOTALL
        )
        deck_m = deck_pat.search(blob)
        deck = re.sub(r"<[^>]+>", "", deck_m.group(1)).strip() if deck_m else ""

        score_m = re.search(r"(\d[\d.]*)\s*/\s*10", blob)
        score = float(score_m.group(1)) if score_m else None

        date_m = re.search(r'data-date="([^"]+)"', blob)
        if not date_m:
            date_m = re.search(r'<span[^>]*class="story-block__date[^"]*"[^>]*>([^<]+)</span>', blob)

        pub_date = parse_date(date_m.group(1)) if date_m else None

        record = {
            "album": title,
            "artist": deck,
            "score": score,
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": [],
            "excerpt": excerpt,
            "site_id": SITE_ID,
            "crawl_status": "ok",
            "type": "review" if score is not None else "feature",
        }

        records.append(record)

    return records


def is_excluded(record):
    text = (record.get("album") or "") + (record.get("excerpt") or "")
    return bool(EXCLUDE_RE.search(text))


def main():
    all_records = []
    seen = set()

    for fname in ["mixmag_asia_reviews_page.html", "mixmag_asia_page2.html"]:
        fpath = WORKSPACE / fname
        if not fpath.exists():
            print(f"SKIP: {fname} not found")
            continue

        with open(fpath) as f:
            html = f.read()
        print(f"\nParsing {fname} ({len(html)} bytes)")

        records = parse_articles(html)
        print(f"  parsed {len(records)} articles")

        for rec in records:
            if rec["url"] in seen:
                continue
            seen.add(rec["url"])

            if rec["pub_date"]:
                try:
                    pub = datetime.fromisoformat(rec["pub_date"])
                    if pub < cutoff:
                        print(f"  [date cutoff] {rec['pub_date']} - {rec['album'][:40]}, stopping")
                        continue
                except Exception:
                    pass

            if is_excluded(rec):
                print(f"  [exclude] {rec['album'][:50]}")
            else:
                all_records.append(rec)
                print(f"  [+] {rec['album'][:55]} score={rec['score']} date={rec['pub_date']}")

    # deduplicate while preserving order
    deduped = []
    seen2 = set()
    for r in all_records:
        if r["url"] not in seen2:
            seen2.add(r["url"])
            deduped.append(r)

    print(f"\nTotal unique: {len(deduped)}")
    with open(OUTPUT, "w") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}")


if __name__ == "__main__":
    main()