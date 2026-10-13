#!/usr/bin/env python3
"""Retry failed RootsWorld article pages via Camoufox."""
import json, re, subprocess, sys, time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from camoufox import Camoufox

BASE = "https://rootsworld.com"
REVIEWER_LINE_RE = re.compile(
    r"^(?:Reviewed\s+by|Review\s+by|By|Interview\s+and\s+review\s+by|"
    r"Recordings\s+and\s+Commentary\s+by|Commentary\s+by)\s+(.+)$", re.I,
)

OUT_PATH = "/home/liyifan/music-record/2026/06/2026-06-10/roots_world_reviews.json"

# Read existing results
with open(OUT_PATH) as f:
    result = json.load(f)

existing_urls = {i["url"] for i in result["items"]}

# Failed URLs to retry
failed = [
    "https://rootsworld.com/reviews/hole-26.shtml",
    "https://rootsworld.com/reviews/prism-prayer-26.shtml",
    "https://rootsworld.com/reviews/guldganger-26.shtml",
    "https://rootsworld.com/reviews/solo-diakite-26.shtml",
    "https://rootsworld.com/reviews/cgs-26.shtml",
    "https://rootsworld.com/reviews/songbook-26.shtml",
    "https://rootsworld.com/reviews/makabe-26.shtml",
    "https://rootsworld.com/reviews/omicil-26.shtml",
    "https://rootsworld.com/reviews/derksen-26.shtml",
    # wvsnake-25.shtml is from 2025, skip
    # soundbites.shtml skip
]

sys.stderr.write(f"[roots_world-retry] Retrying {len(failed)} failed articles via Camoufox\n")

try:
    with Camoufox(headless=True, humanize=True) as b:
        ctx = b.new_context()
        page = ctx.new_page()
        for url in failed:
            sys.stderr.write(f"  Fetching: {url}\n")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(1)
                art_html = page.content()
            except Exception as e:
                sys.stderr.write(f"  ERROR: {e}\n")
                continue

            soup = BeautifulSoup(art_html, "lxml")
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

            body_out = re.split(
                r"Search\s+RootsWorld|Subscribe\s+and\s+Support|Find\s+\w[\w\s]+\s+online\.?$",
                body_text, maxsplit=1
            )[0].strip()

            # Determine type
            item_type = "review"
            if not album:
                if "interview" in body_out.lower()[:400]:
                    item_type = "feature"

            if not album and not artist:
                album = title

            item = {
                "album": album,
                "artist": artist,
                "score": None,
                "url": url,
                "source": "RootsWorld",
                "pub_date": "",
                "tags": "world music",
                "excerpt": body_out[:500] if body_out else "",
                "body": body_out,
                "site_id": "roots_world",
                "crawl_status": "ok",
                "type": item_type,
            }
            if label:
                item["label"] = label
            if reviewer:
                item["reviewer"] = reviewer
            result["items"].append(item)
            sys.stderr.write(f"  + {album or '?'} by {artist or '?'}\n")

except Exception as e:
    sys.stderr.write(f"[roots_world-retry] Camoufox error: {e}\n")

# Update count
result["meta"]["total"] = len(result["items"])
result["meta"]["scraped_at"] = datetime.now(timezone.utc).isoformat()

with open(OUT_PATH, "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

sys.stderr.write(f"[roots_world-retry] Done: {len(result['items'])} total items → {OUT_PATH}\n")
print(json.dumps(result, indent=2, ensure_ascii=False))
