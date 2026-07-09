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
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html import unescape

CAMOFOX_BASE = "http://127.0.0.1:9377"
CAMOFOX_API_KEY = os.environ.get("CAMOFOX_API_KEY", "ed63901c7aca4a85bba34ac6ccf6833e")
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
	headers = {"Authorization": f"Bearer {CAMOFOX_API_KEY}"}
	if data:
		headers["Content-Type"] = "application/json"
	req = urllib.request.Request(
		url, data=data, method=method,
		headers=headers,
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


def create_tab_resilient(user_id, session_key, url):
	"""Create a tab, tolerating the POST /tabs 500 (which can mean the tab
	was actually created on a delayed timeout). Returns (tab_id, list_item_id)
	or raises if no tab was created within the retry budget.
	"""
	# Wipe any prior session for this user_id first.
	try:
		_api("DELETE", f"/sessions/{user_id}?userId={user_id}")
	except Exception:
		pass
	for attempt in range(3):
		try:
			resp = _api("POST", "/tabs", {
				"userId": user_id,
				"sessionKey": session_key,
				"url": url,
			})
			tab_id = resp.get("tabId")
			if tab_id:
				return tab_id, resp.get("listItemId")
		except urllib.error.HTTPError as e:
			if e.code == 500:
				# Maybe a delayed timeout — the tab may exist. Check.
				time.sleep(2)
				try:
					tabs = _api("GET", f"/tabs?userId={user_id}")
					for t in (tabs.get("tabs") or []):
						if "thewildcity.com" in (t.get("url") or "") and t.get("listItemId") == session_key:
							return t["tabId"], t.get("listItemId")
				except Exception:
					pass
				# No recoverable tab — wipe and retry.
				try:
					_api("DELETE", f"/sessions/{user_id}?userId={user_id}")
				except Exception:
					pass
			else:
				raise
		time.sleep(1)
	raise RuntimeError("Failed to create tab after 3 attempts")


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


def parse_dd_mm_yyyy(s):
	"""Parse DD/MM/YYYY (sidebar data-date format) into a date or None."""
	if not s:
		return None
	m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s.strip())
	if not m:
		return None
	try:
		return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
	except ValueError:
		return None


EXTRACT_LISTING_JS = r"""
(() => {
	const results = [];
	const seen = new Set();
	const NEWS_PATH = /\/news\/(\d+)-/;
	const MIXES_PATH = /\/mixes\/(\d+)-/;
	const FEATURES_PATH = /\/features\/(\d+)-/;
	const PODCASTS_PATH = /\/podcasts\/(\d+)-/;
	const SECTION_FOR = (url) => {
		if (NEWS_PATH.test(url)) return 'news';
		if (MIXES_PATH.test(url)) return 'mixes';
		if (FEATURES_PATH.test(url)) return 'features';
		if (PODCASTS_PATH.test(url)) return 'podcasts';
		return null;
	};
	const NUM_FOR = (url) => {
		let m = url.match(NEWS_PATH) || url.match(MIXES_PATH) || url.match(FEATURES_PATH) || url.match(PODCASTS_PATH);
		return m ? parseInt(m[1]) : null;
	};
	// Strategy 1: sidebar feed with data-date (most recent dates, reliable).
	const sidebarItems = [];
	document.querySelectorAll('a[data-date]').forEach(a => {
		const href = a.href || '';
		const section = SECTION_FOR(href);
		if (!section) return;
		const id = NUM_FOR(href);
		if (!id) return;
		const date = (a.getAttribute('data-date') || '').trim();
		const text = a.textContent.trim().split(/[\r\n]+/)[0].trim().slice(0, 250);
		sidebarItems.push({ id, url: href, title: text, date, source: 'sidebar' });
	});
	// Strategy 2: any in-page anchor with a section-prefixed numeric slug,
	// picking up the first paragraph text near the anchor as a title fallback.
	document.querySelectorAll('a').forEach(a => {
		const href = a.href || '';
		const section = SECTION_FOR(href);
		if (!section) return;
		const id = NUM_FOR(href);
		if (!id || seen.has(id)) return;
		seen.add(id);
		const text = a.textContent.trim().split(/[\r\n]+/)[0].trim().slice(0, 250);
		results.push({ id, url: href, title: text, source: 'anchor' });
	});
	return { sidebar: sidebarItems, anchors: results };
})()
"""

GET_ARTICLE_BODY_JS = """
(() => {
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
})()
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
	try:
		tab_id, _ = create_tab_resilient(USER_ID, SESSION_KEY, NEWS_URL)
	except Exception as e:
		sys.stderr.write(f"ERROR: Failed to create tab: {e}\n")
		result = {"meta": {"total":0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
		print(json.dumps(result, indent=2, ensure_ascii=False))
		sys.exit(1)

	if not tab_id:
		sys.stderr.write("ERROR: Failed to create tab\n")
		result = {"meta": {"total":0, "scraped_at": today.isoformat(), "cutoff_date": cutoff_date.isoformat()}, "items": []}
		print(json.dumps(result, indent=2, ensure_ascii=False))
		sys.exit(1)

	all_items = []
	try:
		time.sleep(2)
		all_articles_raw = []  # {id, url, title, date?, source_sidebar}
		seen_ids = set()

		for page_num in range(1, pages +1):
			if page_num ==1:
				url = NEWS_URL
			else:
				url = f"{NEWS_URL}?offset={10 * (page_num -1)}"

			sys.stderr.write(f"\n=== Listing page {page_num}: {url} ===\n")

			if page_num >1:
				_api("POST", f"/tabs/{tab_id}/navigate", {"url": url, "userId": USER_ID})
				time.sleep(2)

			resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
				"expression": EXTRACT_LISTING_JS,
				"userId": USER_ID,
			})
			payload = resp.get("result") or {}
			sidebar = payload.get("sidebar") or []
			anchors = payload.get("anchors") or []
			sys.stderr.write(f"Found {len(sidebar)} sidebar items, {len(anchors)} anchors on page {page_num}\n")

			# Index sidebar by id for date lookup
			sidebar_by_id = {item["id"]: item for item in sidebar}

			# First add sidebar items (have date)
			for item in sidebar:
				if item["id"] in seen_ids:
					continue
				seen_ids.add(item["id"])
				if "/podcasts/" in item["url"]:
					continue
				if NON_MUSIC_RE.search(item.get("title", "")):
					continue
				date = parse_dd_mm_yyyy(item.get("date", ""))
				if date and date < cutoff_date:
					continue  # out of window
				all_articles_raw.append({
					"id": item["id"],
					"url": item["url"],
					"title": item["title"],
					"date": date.isoformat() if date else None,
				})
			# Then anchor-only items (no sidebar entry yet)
			for item in anchors:
				if item["id"] in seen_ids:
					continue
				seen_ids.add(item["id"])
				if "/podcasts/" in item["url"]:
					continue
				if NON_MUSIC_RE.search(item.get("title", "")):
					continue
				all_articles_raw.append({
					"id": item["id"],
					"url": item["url"],
					"title": item["title"],
					"date": None,
				})

		sys.stderr.write(f"\nTotal unique article candidates (after date/podcast/non-music filters): {len(all_articles_raw)}\n")

		if not args.no_article_pages:
			for i, art in enumerate(all_articles_raw):
				url = art["url"]
				known_date = art.get("date")  # may be None — we'll fall through to body parsing
				sys.stderr.write(f"\n[{i+1}/{len(all_articles_raw)}] id={art['id']} {url} (known_date={known_date})\n")

				# type: review only when title explicitly says "Review:" — Wild City
				# runs feature-style writeups almost everywhere (news/mixes/features).
				title_lower = art.get("title", "").lower()
				if title_lower.startswith("review:") or " review:" in title_lower[:20]:
					item_type = "review"
				else:
					item_type = "feature"

				try:
					# Skip items already filtered to be outside the window via sidebar date.
					if known_date:
						try:
							kd = datetime.strptime(known_date, "%Y-%m-%d").date()
							if kd < cutoff_date:
								sys.stderr.write(f" SKIP (sidebar date {known_date} before cutoff {cutoff_date})\n")
								continue
						except ValueError:
							pass

					_api("POST", f"/tabs/{tab_id}/navigate", {"url": url, "userId": USER_ID})
					time.sleep(1.5)

					resp = _api("POST", f"/tabs/{tab_id}/evaluate", {
						"expression": GET_ARTICLE_BODY_JS,
						"userId": USER_ID,
					})
					detail = resp.get("result") or {}
					if not detail.get("found"):
						sys.stderr.write(" WARN: article body not found, using listing title\n")
						detail = {"title": art["title"], "body": "", "dateText": ""}

					title = (detail.get("title") or art["title"] or "").strip()
					body = (detail.get("body") or "").strip()
					date_text = (detail.get("dateText") or "").strip()

					if known_date:
						pub_date = known_date
					elif date_text:
						pub_date = parse_date(date_text)
						if pub_date:
							try:
								item_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
								if item_date < cutoff_date:
									sys.stderr.write(f" SKIP (body date {pub_date} before cutoff {cutoff_date})\n")
									continue
							except ValueError:
								pass
					else:
						pub_date = None

					# Final fallback: today
					if not pub_date:
						pub_date = today.isoformat()

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
				title_lower = art.get("title", "").lower()
				if title_lower.startswith("review:") or " review:" in title_lower[:20]:
					item_type = "review"
				else:
					item_type = "feature"
				pub_date = art.get("date") or today.isoformat()
				item = {
					"album": art["title"][:250],
					"artist": "Wild City Editors",
					"score": None,
					"url": art["url"],
					"source": SOURCE,
					"pub_date": pub_date,
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
					"hours_scanned": int(args.days * 24),
				},
				"items": all_items,
			}
		print(json.dumps(result, indent=2, ensure_ascii=False))
		sys.stderr.write(f"\nTotal: {len(all_items)} items\n")

	finally:
		try:
			_api("DELETE", f"/tabs/{tab_id}?userId={USER_ID}")
			sys.stderr.write(f"Closed tab {tab_id}\n")
		except Exception as e:
			sys.stderr.write(f"WARNING: Failed to close tab: {e}\n")


if __name__ == "__main__":
	main()
