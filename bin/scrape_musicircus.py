#!/usr/bin/env python3
"""
scrape_musicircus.py — Camoufox-based scraper for musicircus.

musicircus (musicircus.on.coocan.jp) — Japanese personal site covering
jazz, avant-garde, contemporary music. No RSS feed. Site is a static HTML
page with a table of "Update" entries showing dates in format YYYY.M.D.
Individual article pages are at links like /2005/20051209.html.

Strategy:
  1. Open tab on the home page.
  2. Check for cookie/consent wall — click Accept if present.
  3. Look at the Update table for any entries within 36h window.
  4. For each recent entry, navigate to the article page and fetch body.
  5. Output JSON envelope {meta, items} to stdout.

Usage:
  python3 scrape_musicircus.py [--days 1.5] [--max-items 20]
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# ── Configuration ──────────────────────────────────────────────────────
CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "")

TARGET_URL = "http://musicircus.on.coocan.jp"

SITE_ID = "musicircus"
SOURCE = "musicircus.on.coocan.jp"
TAGS = "jazz,avant-garde,contemporary,experimental,japan"
USER_ID = "scraper_musicircus"
SESSION_KEY = "session_musicircus"

# Non-music tokens to skip
NON_MUSIC_RE = re.compile(r"\((BLU-RAY|UHD|VOD|DVD)\)", re.IGNORECASE)

# ── Helpers ────────────────────────────────────────────────────────────


def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Make a JSON API call to the Camoufox REST server."""
    url = f"{CAMOFOX_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
    )
    if data:
        req.add_header("Content-Type", "application/json")
    if CAMOFOX_API_KEY:
        req.add_header("Authorization", f"Bearer {CAMOFOX_API_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {e.read().decode()[:300]}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
        raise


def close_tab(tab_id: str) -> None:
    """Safely close a Camoufox tab."""
    if tab_id:
        try:
            _api("DELETE", f"/tabs/{tab_id}?userId={USER_ID}")
            sys.stderr.write(f"  Closed tab {tab_id}\n")
        except Exception as e:
            sys.stderr.write(f"  WARNING: Failed to close tab: {e}\n")


def create_tab(url: str) -> str | None:
    """Create a Camoufox tab and navigate to URL. Returns tab_id or None."""
    sys.stderr.write(f"  Creating tab for {url[:80]}...\n")
    try:
        tab_resp = _api("POST", "/tabs", {
            "userId": USER_ID,
            "sessionKey": SESSION_KEY,
            "url": url,
        })
        tab_id = tab_resp.get("tabId")
        if not tab_id:
            sys.stderr.write("  ERROR: No tabId in response\n")
            return None
        sys.stderr.write(f"  Tab {tab_id} created, waiting for page load...\n")
        time.sleep(8)
        return tab_id
    except Exception as e:
        sys.stderr.write(f"  ERROR creating tab: {e}\n")
        return None


def evaluate_js(tab_id: str, expression: str):
    """Evaluate JS expression in a Camoufox tab. Returns the result value."""
    try:
        resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
            "userId": USER_ID, "expression": expression})
        return resp.get("result")
    except Exception as e:
        sys.stderr.write(f"  ERROR evaluating JS: {e}\n")
        return None


def navigate(tab_id: str, url: str) -> bool:
    """Navigate an existing tab to a new URL."""
    try:
        _api("POST", f"/tabs/{tab_id}/navigate", {"userId": USER_ID, "url": url})
        sys.stderr.write(f"  Navigated to {url[:80]}...\n")
        time.sleep(6)
        return True
    except Exception as e:
        sys.stderr.write(f"  ERROR navigating tab: {e}\n")
        return False


def fetch_body(tab_id: str) -> str:
    """Fetch full body text from the current page via JS evaluation."""
    js = """
    () => {
        const article = document.querySelector('article');
        if (article) return article.innerText.slice(0, 12000);
        return document.body.innerText.slice(0, 12000);
    }
    """
    try:
        result = evaluate_js(tab_id, js)
        if result is None:
            return ""
        return str(result).strip()
    except Exception as e:
        sys.stderr.write(f"  ERROR fetching body: {e}\n")
        return ""


def check_consent(tab_id: str) -> None:
    """Check for a cookie/consent wall and click Accept if present."""
    js_check = """() => {
        const buttons = document.querySelectorAll('button, a, input[type="submit"], [role="button"]');
        const acceptTexts = ['accept', 'agree', 'consent', 'ok', 'i agree', 'allow all', 'accept all',
                             '同意', '許可', '承諾', '確認', 'わかった', 'はい'];
        const accept = [];
        buttons.forEach((b, i) => {
            const txt = (b.textContent || b.value || '').toLowerCase().trim();
            for (const t of acceptTexts) {
                if (txt.includes(t)) {
                    accept.push({index: i, text: b.textContent.trim().slice(0, 50)});
                    break;
                }
            }
        });
        return accept.length > 0 ? accept : null;
    }"""
    result = evaluate_js(tab_id, js_check)
    if result and len(result) > 0:
        btn = result[0]
        sys.stderr.write(f"  Cookie wall found: '{btn['text']}' — clicking button #{btn['index']}...\n")
        click_js = f"""() => {{
            const buttons = document.querySelectorAll('button, a, input[type="submit"], [role="button"]');
            if (buttons[{btn['index']}]) {{
                buttons[{btn['index']}].click();
                return 'clicked';
            }}
            return 'not found';
        }}"""
        click_result = evaluate_js(tab_id, click_js)
        sys.stderr.write(f"  Consent click result: {click_result}\n")
        time.sleep(2)
    else:
        sys.stderr.write("  No cookie wall detected.\n")


def parse_musicircus_date(text: str) -> str | None:
    """Parse musicircus date formats: 'YYYY.M.D' or 'YYYY/M/D'.
    Returns ISO date string (YYYY-MM-DD) or None.
    """
    text = (text or "").strip()
    # Try YYYY.M.D
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.date().isoformat()
        except ValueError:
            return None
    # Try YYYY/M/D
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.date().isoformat()
        except ValueError:
            return None
    return None


def get_page_html(tab_id: str) -> str:
    """Get the full page HTML via JS."""
    js = """() => document.documentElement.outerHTML"""
    result = evaluate_js(tab_id, js)
    return str(result) if result else ""


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape musicircus")
    parser.add_argument("--days", type=float, default=1.5,
                        help="Lookback window in days (default: 1.5 = 36h)")
    parser.add_argument("--max-items", type=int, default=20,
                        help="Max items to fetch (default: 20)")
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_date = cutoff.date()
    sys.stderr.write(f"  Cutoff: {cutoff_date.isoformat()} ({args.days} days ago)\n")
    sys.stderr.write(f"  Max items: {args.max_items}\n")

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    items = []
    tab_id = None

    try:
        # 1. Open home page
        tab_id = create_tab(TARGET_URL)
        if not tab_id:
            sys.stderr.write("  FATAL: Could not create tab\n")
            sys.exit(1)

        # 2. Check for cookie wall
        check_consent(tab_id)

        # 3. Get the page HTML and look for Update table / recent entries
        html = get_page_html(tab_id)
        sys.stderr.write(f"  Page HTML length: {len(html)} chars\n")

        # musicircus home page has an "Update" table. Entries look like:
        # <tr><td>2025.12.9</td><td><a href="..." title="...">some text</a></td></tr>
        # or simpler: <td>2025.12.9</td><td><a href="2005/20051209.html">Title</a></td>

        # Strategy: find all table rows with date cells
        # Look for links with text that might be article titles
        # Extract: date, title, url

        # First, try to find the Update table
        extract_js = """() => {
            const updates = [];

            // Find tables on the page
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                for (const row of rows) {
                    const cells = row.querySelectorAll('td, th');
                    if (cells.length < 2) continue;

                    const firstCell = cells[0].textContent.trim();
                    // Try to parse as date YYYY.M.D or YYYY/M/D
                    const dateMatch = firstCell.match(/^(\\d{4})[./](\\d{1,2})[./](\\d{1,2})/);
                    if (!dateMatch) continue;

                    const dateStr = firstCell;
                    const link = cells[1].querySelector('a');
                    if (!link) continue;

                    updates.push({
                        date: dateStr,
                        url: link.href,
                        title: (link.textContent || link.title || '').trim(),
                        allText: cells[1].textContent.trim()
                    });
                }
            }

            // If no table found, try harder — look for any links with date-like preceding text
            if (updates.length === 0) {
                const allLinks = document.querySelectorAll('a');
                for (const link of allLinks) {
                    const parent = link.parentElement;
                    if (!parent) continue;
                    const prev = parent.previousElementSibling || parent.parentElement?.previousElementSibling;
                    if (!prev) continue;

                    const prevText = prev.textContent.trim();
                    const dateMatch = prevText.match(/^(\\d{4})[./](\\d{1,2})[./](\\d{1,2})/);
                    if (!dateMatch) continue;

                    updates.push({
                        date: prevText,
                        url: link.href,
                        title: (link.textContent || link.title || '').trim(),
                        allText: parent.textContent.trim()
                    });
                }
            }

            return updates;
        }"""
        entries = evaluate_js(tab_id, extract_js)
        if entries is None:
            entries = []

        sys.stderr.write(f"  Found {len(entries)} entries in Update table\n")

        # Filter by cutoff date, skip non-music
        recent_entries = []
        for entry in entries:
            iso_date = parse_musicircus_date(entry.get("date", ""))
            if not iso_date:
                continue
            entry_date = datetime.strptime(iso_date, "%Y-%m-%d").date()
            if entry_date < cutoff_date:
                continue
            title = entry.get("title", "")
            all_text = entry.get("allText", "")
            full_text = f"{title} {all_text}"
            if NON_MUSIC_RE.search(full_text):
                sys.stderr.write(f"  SKIP (non-music): {title}\n")
                continue
            recent_entries.append(entry)

        # Sort by date descending, newest first
        recent_entries.sort(key=lambda e: parse_musicircus_date(e.get("date", "")) or "", reverse=True)

        # Limit
        recent_entries = recent_entries[:args.max_items]

        sys.stderr.write(f"  Recent entries within cutoff: {len(recent_entries)}\n")

        for entry in recent_entries:
            title = entry.get("title", "")
            url = entry.get("url", "")
            entry_date = parse_musicircus_date(entry.get("date", ""))

            sys.stderr.write(f"\n  --- Processing: {title} ({entry_date}) ---\n")

            # Navigate to the article page
            if not navigate(tab_id, url):
                sys.stderr.write(f"  FAILED to navigate to {url}\n")
                continue

            # Fetch body
            body = fetch_body(tab_id)

            # Determine type: guess based on content
            body_lower = body.lower()
            excerpt = body[:300].strip()

            if any(kw in body_lower for kw in ["review", "レビュー", "評"]):
                item_type = "review"
            elif any(kw in body_lower for kw in ["interview", "インタビュー", "対談", "特集"]):
                item_type = "feature"
            else:
                item_type = "feature"

            # Extract artist and album from title
            # musicircus titles may be like "Artist - Album" or just article titles
            artist = ""
            album = title
            sep_match = re.search(r"\s*[—–\-:]\s*", title)
            if sep_match:
                artist = title[:sep_match.start()].strip()
                album = title[sep_match.end():].strip()

            # Score — personal blog, no explicit rating system
            score = None

            item = {
                "album": album,
                "artist": artist,
                "score": score,
                "url": url,
                "source": SOURCE,
                "pub_date": entry_date,
                "tags": TAGS,
                "excerpt": excerpt[:500],
                "body": body,
                "site_id": SITE_ID,
                "crawl_status": "ok",
                "type": item_type,
            }
            items.append(item)

        # 4. Build output
        output = {
            "meta": {
                "total": len(items),
                "scraped_at": scraped_at,
                "cutoff_date": cutoff.isoformat(),
                "hours_scanned": args.days * 24,
                "site": "musicircus",
                "source": SOURCE,
                "site_id": SITE_ID,
                "crawl_status": "ok",
            },
            "items": items,
        }

        print(json.dumps(output, ensure_ascii=False, indent=2))

    finally:
        if tab_id:
            close_tab(tab_id)


if __name__ == "__main__":
    main()
