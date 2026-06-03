#!/usr/bin/env python3
"""
scrape_bandwagon_asia.py — Camoufox-based scraper for Bandwagon Asia.

Scrapes articles from Review, Listen, and News categories.
Outputs structured JSON to stdout.
"""
import json, urllib.request, sys, time, re
from datetime import datetime, timezone, timedelta

CAMOFOX = "http://127.0.0.1:9377"

def req(method, path, body=None):
    url = f"{CAMOFOX}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read())

def get_articles_from_listing(url):
    """Extract article links from a category listing page."""
    tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":url})
    tid = tab.get("tabId","")
    time.sleep(2)
    js = """() => {
        const items = [];
        const blocks = document.querySelectorAll('.article-block');
        blocks.forEach(b => {
            const link = b.querySelector('.article-block__title');
            const title = link ? link.textContent.trim() : '';
            const url = link ? link.href : '';
            if (title && url) items.push({title, url});
        });
        return JSON.stringify(items);
    }"""
    resp = req("POST", f"/tabs/{tid}/evaluate", {"expression": js})
    arts = json.loads(resp.get("result","[]"))
    req("DELETE", f"/tabs/{tid}")
    return arts

def fetch_article(tab_id, url):
    """Navigate to article page and extract content."""
    try:
        req("POST", f"/tabs/{tab_id}/navigate", {"url": url})
        time.sleep(2)
    except:
        return None
    return tab_id

def extract_article_data(tab_id):
    """Extract metadata and body from the current article page."""
    js = """() => {
        const timeEl = document.querySelector('time');
        const dt = timeEl ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim()) : '';
        const h1 = document.querySelector('h1');
        const title = h1 ? h1.textContent.trim() : '';
        const authorEl = document.querySelector('[rel=author], .author, .byline, [class*=author], [class*=byline]');
        const author = authorEl ? authorEl.textContent.trim() : '';

        const article = document.querySelector('article') || document.querySelector('.article-content') || document.querySelector('.content') || document.querySelector('main');
        const body = article ? article.innerText.slice(0, 10000) : document.body.innerText.slice(0, 10000);
        return JSON.stringify({date: dt, title, author, body: body.slice(0,10000), bodyLen: body.length});
    }"""
    resp = req("POST", f"/tabs/{tab_id}/evaluate", {"expression": js})
    raw = resp.get("result", "{}")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw

def parse_date(dt_str):
    """Parse ISO date string to datetime."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except:
        pass
    # Try other formats
    for fmt in ["%Y-%m-%d", "%B %d, %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(dt_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except:
            pass
    return None

def clean_text(text):
    """Remove common junk suffixes from text fields."""
    text = re.sub(r'\s+', ' ', text).strip()
    for junk in ["By Bandwagon", "— watch", " — gig report", "along with"]:
        idx = text.rfind(junk)
        if idx > len(text) // 2:
            text = text[:idx].strip()
    return text

def infer_artist_album(title, body):
    """Try to extract artist and album from title/body."""
    title_lower = title.lower()
    body_lower = body.lower()

    artist = ""
    album = clean_text(title)

    # Common patterns: "Artist – Album", "Artist - Album", "Artist: Album"
    for sep in [" — ", " – ", " - ", ": "]:
        parts = title.split(sep, 1)
        if len(parts) == 2:
            first, second = parts[0].strip(), parts[1].strip()
            # Check if first part looks like an artist name (not a verb)
            if len(first) > 2 and len(second) > 2 and not first.startswith("'") and not first.endswith("'"):
                if not any(v in first.lower() for v in ["how ", "the ", "what ", "why ", "when ", "review", "news", "first"]):
                    artist = first
                    album = clean_text(second)
                    break

    # Clean up album
    if not album or len(album) < 5:
        album = clean_text(title)

    return artist, album

def is_music_article(title, body):
    """Check if article is music-related."""
    skip_keywords = [
        "(blu-ray)", "(uhd)", "(vod)", "(dvd)",
        "film review", "movie review", "tv review", "gaming"
    ]
    title_lower = title.lower()
    for kw in skip_keywords:
        if kw in title_lower:
            return False
    return True

def determine_type(title, body):
    """Determine article type."""
    title_lower = title.lower()
    body_lower = body.lower()

    # Check for review patterns
    review_indicators = ["album review", "ep review", "review:", "track review", "single review"]
    for ind in review_indicators:
        if ind in title_lower or ind in body_lower:
            return "review"

    # Check for tracklist/album/EP patterns
    tracklist_indicators = ["tracklist", "track list", "album track"]
    for ind in tracklist_indicators:
        if ind in title_lower or ind in body_lower:
            return "tracklist"

    # Check for listen/feature
    feature_indicators = ["listen", "new music", "premiere", "exclusive", "interview", "conversation"]
    for ind in feature_indicators:
        if ind in title_lower:
            return "feature"

    return "feature"  # default

def main():
    today = datetime.now(timezone.utc)
    cutoff_date = today - timedelta(hours=36)

    sys.stderr.write(f"Bandwagon Asia scraper — Cutoff: {cutoff_date.isoformat()}\n")

    # Collect articles from all relevant categories
    all_articles = []
    seen_urls = set()

    categories = [
        ("/categories/listen", "Listen"),
        ("/categories/review", "Reviews"),
        ("/categories/news", "News"),
    ]

    for path, label in categories:
        try:
            arts = get_articles_from_listing(f"https://www.bandwagon.asia{path}")
            sys.stderr.write(f"  {label}: {len(arts)} articles\n")
            for a in arts:
                url = a.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    a["category"] = label
                    all_articles.append(a)
        except Exception as e:
            sys.stderr.write(f"  Error on {label}: {e}\n")

    # Check page 2 for news
    try:
        arts2 = get_articles_from_listing("https://www.bandwagon.asia/categories/news?page=2")
        for a in arts2:
            url = a.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                a["category"] = "News"
                all_articles.append(a)
    except:
        pass

    sys.stderr.write(f"Total unique articles: {len(all_articles)}\n")

    if not all_articles:
        result = {
            "meta": {"total": 0, "scraped_at": today.date().isoformat(), "cutoff_date": cutoff_date.date().isoformat()},
            "items": []
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.stderr.write("Bandwagon Asia: 0 items (no articles found)\n")
        return

    # Create a tab for article extraction
    tab = req("POST", "/tabs", {"userId":"bw","sessionKey":"bw","url":"about:blank"})
    tab_id = tab.get("tabId", "")
    if not tab_id:
        result = {
            "meta": {"total": 0, "scraped_at": today.date().isoformat(), "cutoff_date": cutoff_date.date().isoformat()},
            "items": []
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    items = []
    try:
        for idx, a in enumerate(all_articles):
            url = a["url"]
            title = a["title"]
            sys.stderr.write(f"  [{idx+1}/{len(all_articles)}] {title[:50]}...\n")

            try:
                fetch_article(tab_id, url)
                data = extract_article_data(tab_id)

                dt_str = data.get("date", "")
                pub_date = parse_date(dt_str)
                body = data.get("body", "")

                if pub_date and pub_date < cutoff_date:
                    sys.stderr.write(f"    SKIP: older than cutoff ({pub_date.isoformat()} < {cutoff_date.isoformat()})\n")
                    continue

                if not is_music_article(title, body):
                    sys.stderr.write(f"    SKIP: non-music article\n")
                    continue

                # Try to extract artist/album
                artist, album = infer_artist_album(title, body)

                # Determine type
                article_type = determine_type(title, body)

                # Excerpt is first 500 chars of body
                excerpt = re.sub(r'\s+', ' ', body[:500]).strip()

                # For bandwagon, if we can't parse artist/album, use title as album
                if not artist and not album:
                    album = title

                source_cat = a.get("category", "News")
                tags = "asia,pop"
                if "listen" in source_cat.lower():
                    tags = "asia,listen,pop"
                elif "review" in source_cat.lower():
                    tags = "asia,review,pop"

                items.append({
                    "album": album,
                    "artist": artist,
                    "score": None,  # No numeric ratings
                    "url": url,
                    "source": "Bandwagon Asia",
                    "pub_date": pub_date.isoformat() if pub_date else dt_str,
                    "tags": tags,
                    "excerpt": excerpt[:500],
                    "body": body,
                    "site_id": "bandwagon_asia",
                    "crawl_status": "success",
                    "type": article_type,
                })
            except Exception as e:
                sys.stderr.write(f"    ERROR: {e}\n")
                continue

    finally:
        try:
            req("DELETE", f"/tabs/{tab_id}")
        except:
            pass

    result = json.dumps({
        "meta": {
            "total": len(items),
            "scraped_at": today.date().isoformat(),
            "cutoff_date": cutoff_date.date().isoformat(),
        },
        "items": items
    }, indent=2, ensure_ascii=False)
    print(result)
    sys.stderr.write(f"Bandwagon Asia: {len(items)} items\n")

if __name__ == "__main__":
    main()
