#!/usr/bin/env python3
"""scrape_wildcity.py - Camoufox-based scraper for Wild City (thewildcity.com).

Wild City is an Indian music publication (south asian / alternative / electronic).
No RSS feed. Uses Camoufox (Firefox-based) to handle JS rendering.

Strategy:
1. /news page (offset=0) + /news?offset=10 (only2 pages allowed by spec)
2. Extract article URLs from anchor links
3. Visit each article; body in article.layout-article > div.row > .span-w-12 (2nd)
4. Filter by36h cutoff via pub_date parsed from first <p>
5. Output structured JSON in {meta, items} envelope

Usage:
 python3 scrape_wildcity.py [--pages2] [--days1.5]
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape

CAMOFOX_BASE = "http://127.0.0.1:9377"
NEWS_URL = "https://www.thewildcity.com/news"

SITE_ID = "wild_city"
SOURCE = "Wild City"
TAGS_DEFAULT = "south asian,alternative,electronic"
USER_ID = "scraper_wildcity"
SESSION_KEY = "session_wc"

MONTHS = {
	"january":1, "february":2, "march":3, "april":4, "may":5, "june":6,
	"july":7, "august":8, "september":9, "october":10, "november":11, "december":12,
	"jan":1, "feb":2, "mar":3, "apr":4, "may":5, "jun":6,
	"jul":7, "aug":8, "sep":9, "oct":10, "nov":11, "dec":12,
}

NON_MUSIC_RE = re.compile(r'\(BLU-RAY\)|\(UHD\)|\(VOD\)|\(DVD\)', re.IGNORECASE)


def _api(method, path, body=None):
	url = f"{CAMOFOX_BASE}{path}"
	data = json.dumps(body).encode("utf-8") if body else None
	req = urllib.request.Request(
		url, data=data, method=method,
		headers={"Content-Type": "application/json"} if data else {},
	)
	try:
		with urllib.request.urlopen(req, timeout=60) as resp:
			return json.loads(resp.read().decode("utf-8"))
	except urllib.error.HTTPError as e:
		body_text = e.read().decode()[:500]
		sys.stderr.write(f"[ERROR] HTTP {e.code} on {method} {path}: {body_text}\n")
		raise
	except Exception as e:
		sys.stderr.write(f"[ERROR] {method} {path}: {e}\n")
		raise


def parse_date(date_str):
	date_str = date_str.strip()
	today = datetime.now(timezone.utc).date()
	if date_str.lower() == "today":
		return today.isoformat()
	if date_str.lower() == "yesterday":
		return (today - timedelta(days=1)).isoformat()
	# Strip leading ordinal suffix like "4th", "1st"
	date_str = re.sub(r'(\d+)(st|nd|rd|th)\b', r'\1', date_str)
	parts = date_str.replace(",", "").split()
	if len(parts) >=3:
		day_str = parts[0]
		month_name = parts[1].lower().rstrip(".")
		year_str = parts[2]
		month = MONTHS.get(month_name)
		if month and day_str.isdigit() and year_str.isdigit():
			try:
				return datetime(int(year_str), month, int(day_str)).date().isoformat()
			except ValueError:
				pass
	return None


EXTRACT_LISTING_JS = """
() => {
	const results = [];
	const seen = new Set();
	document.querySelectorAll('a').forEach(a => {
		const href = a.href || '';
		const m = href.match(/\\/news\\/(\\d+)-/);
		if (!m) return;
		const id = m[1];
		if (seen.has(id)) return;
		seen.add(id);
		const text = a.textContent.trim();
		const title = text.split(/\\n/)[0].trim().slice(0,250);
		results.push({ id: parseInt(id), url: href, title: title });
	});
	return results;
}
"""

GET_ARTICLE_BODY_JS = """
() => {
	const article = document.querySelector('article.layout-article');
	if (!article) return { found: false };
	const rows = article.querySelectorAll('.row');
	if (!rows.length) return { found: false };
	const divs = rows[0].querySelectorAll('.span-w-12');
	if (divs.length <2) return { found: false };
	const div2 = divs[1];
	const paras = Array.from(div2.querySelectorAll('p'));
	const dateText = paras.length ? paras[0].textContent.trim() : '';
	const bodyParas = paras.slice(1).map(p => p.textContent.trim()).filter(t => t.length >0);
	const body = bodyParas.join('\\n\\n');
	const h1 = document.querySelector('h1');
	const title = h1 ? h1.textContent.trim() : '';
	return { found: true, dateText: dateText, body: body, title: title };
}
"""


def main():
	parser = argparse.ArgumentParser(description="Scrape Wild City music articles")
	parser.add_argument("--pages", type=int, default=2, help="Number of listing pages (max2)")
	parser.add_argument("--days", type=float, default=1.5, help="Max age in days")
	parser.add_argument("--date", type=str, default=None, help="Explicit cutoff date YYYY-MM-DD")
	parser.add_argument("--no-article-pages", action="store_true", help="Skip visiting individual article pages")
	args = parser.parse_args()
	pages = min(args.pages,2)

	today = datetime.now(timezone.utc).date()
	if args.date:
		try:
			cutoff_date = datetime.strptime(args.date, "%Y-%m-%d").date()
		except ValueError:
			sys.stderr.write("ERROR: Invalid --date. Use YYYY-MM-DD.\n")
			sys.exit(1)
	else:
		cutoff_date = today - timedelta(days=args.days)

	sys.stderr.write(
		f"Wild City scraper - Today: {today}, Cutoff: {cutoff_date}, Pages: {pages}\n"
	)

	sys.stderr.write("Creating tab and navigating to /news...\n")
	tab_resp = _api("POST", "/tabs", {
		"userId": USER_ID,
		"sessionKey": SESSION_KEY,
		"url": NEWS_URL,
	})
	tab_id = tab_resp.get("tabId")
	if not tab_id:
		sys.stderr.write("ERROR: Failed to create tab\n")
		result = {"meta": {"total":0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
		print(json.dumps(result, indent=2, ensure_ascii=False))
		sys.exit(1)

	all_items = []
	try:
		time.sleep(2)
		all_articles_raw = []
		seen_ids = set()

		for page_num in range(1, pages +1):
			if page_num ==1:
				url = NEWS_URL
			else:
				url = f"{NEWS_URL}?offset={10 * (page_num -1)}"

			sys.stderr.write(f"\n=== Listing page {page_num}: {url} ===\n")

			if page_num >1:
				_api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
				time.sleep(2)

			resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
				"expression": EXTRACT_LISTING_JS,
			})
			articles = resp.get("result") or []
			sys.stderr.write(f"Found {len(articles)} articles on page {page_num}\n")

			for art in articles:
				if art["id"] not in seen_ids:
					seen_ids.add(art["id"])
					all_articles_raw.append(art)

		sys.stderr.write(f"\nTotal unique articles: {len(all_articles_raw)}\n")

		if not args.no_article_pages:
			for i, art in enumerate(all_articles_raw):
				url = art["url"]
				sys.stderr.write(f"\n[{i+1}/{len(all_articles_raw)}] id={art['id']} {url}\n")

				item_type = "feature" if "/features/" in url else "review"

				if NON_MUSIC_RE.search(art.get("title", "")):
					sys.stderr.write(" SKIP (non-music title)\n")
					continue

				try:
					_api("POST", f"/tabs/{tab_id}/navigate", {"url": url})
					time.sleep(1.5)

					resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
						"expression": GET_ARTICLE_BODY_JS,
					})
					detail = resp.get("result") or {}
					if not detail.get("found"):
						sys.stderr.write(" WARN: article body not found, using listing title\n")
						detail = {"title": art["title"], "body": "", "dateText": ""}

					title = (detail.get("title") or art["title"] or "").strip()
					body = (detail.get("body") or "").strip()
					date_text = (detail.get("dateText") or "").strip()

					pub_date = parse_date(date_text) if date_text else None
					if pub_date:
						try:
							item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
							if item_date < cutoff_date:
								sys.stderr.write(f" SKIP (date {pub_date} before cutoff {cutoff_date})\n")
								continue
						except ValueError:
							pass
					else:
						pub_date = today.isoformat() # fallback if no parseable date

					score = None
					excerpt = body[:500] if body else ""

					item = {
						"album": title if title else "Unknown",
						"artist": "Wild City Editors",
						"score": score,
						"url": url,
						"source": SOURCE,
						"pub_date": pub_date,
						"tags": TAGS_DEFAULT,
						"excerpt": excerpt,
						"body": body,
						"site_id": SITE_ID,
						"crawl_status": "success" if body else "partial",
						"type": item_type,
					}
					all_items.append(item)
					sys.stderr.write(f" OK - {title[:60]}... ({pub_date}, {len(body)} chars)\n")

				except Exception as e:
					sys.stderr.write(f" ERROR: {e}\n")
					continue
		else:
			for art in all_articles_raw:
				item_type = "feature" if "/features/" in art["url"] else "review"
				item = {
					"album": art["title"][:250],
					"artist": "Wild City Editors",
					"score": None,
					"url": art["url"],
					"source": SOURCE,
					"pub_date": today.isoformat(),
					"tags": TAGS_DEFAULT,
					"excerpt": "",
					"body": "",
					"site_id": SITE_ID,
					"crawl_status": "listing_only",
					"type": item_type,
				}
				all_items.append(item)

		result = {
			"meta": {
				"total": len(all_items),
				"scraped_at": datetime.now(timezone.utc).isoformat(),
				"cutoff_date": cutoff_date.isoformat(),
			},
			"items": all_items,
		}
		print(json.dumps(result, indent=2, ensure_ascii=False))
		sys.stderr.write(f"\nTotal: {len(all_items)} items\n")

	finally:
		try:
			_api("DELETE", f"/tabs/{tab_id}")
			sys.stderr.write(f"Closed tab {tab_id}\n")
		except Exception as e:
			sys.stderr.write(f"WARNING: Failed to close tab: {e}\n")


if __name__ == "__main__":
	main()
