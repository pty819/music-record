#!/usr/bin/env python3
"""Parse Mixmag Asia from saved HTML files."""
from pathlib import Path
import json, re
from datetime import datetime, timedelta
from html.parser import HTMLParser

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
    for fmt in ["%Y-%m-%d", "%d %b %Y", "%B %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except Exception:
            pass
    return None

class MixmagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_article = False
        self.in_time = False
        self.in_h2 = False
        self.in_h3 = False
        self.in_deck = False
        self.in_story_headline = False
        self.stack = []
        self.articles = []
        self.current = None
        self.capturing_text = ""
        self.capture_target = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        article_classes = ["story-block", "js-article"]
        
        if tag == "article" and any(c in cls for c in article_classes):
            self.in_article = True
            self.current = {"href": "", "title": "", "deck": "", "date": "", "score": None}
        
        if self.in_article:
            if tag == "a" and "/read/" in attrs_dict.get("href", ""):
                self.current["href"] = attrs_dict.get("href", "")
            elif tag == "time":
                self.in_time = True
            elif tag in ("h2", "h3"):
                self.in_h2 = True
                self.in_h3 = (tag == "h3")
                self.capturing_text = ""
            elif "story-block__headline" in cls or "story-block__subheading" in cls:
                self.capture_target = "headline"
                self.capturing_text = ""
            elif "story-block__deck" in cls:
                self.capture_target = "deck"
                self.capturing_text = ""
            elif "story-block__date" in cls:
                self.capture_target = "date"
                self.capturing_text = ""
            elif "story-block__subheading" in cls:
                self.capture_target = "deck"
                self.capturing_text = ""
    
    def handle_endtag(self, tag):
        if self.in_article:
            if tag == "article":
                self.in_article = False
                self.articles.append(self.current)
                self.current = None
            elif tag in ("h2", "h3"):
                if self.current and self.capturing_text:
                    self.current["title"] = self.capturing_text.strip()
                self.in_h2 = False
                self.in_h3 = False
                self.capturing_text = ""
            elif self.capture_target and tag in ("div", "span", "p"):
                if self.capture_target == "headline":
                    if self.current and not self.current.get("title"):
                        self.current["title"] = self.capturing_text.strip()
                elif self.capture_target == "deck":
                    if self.current:
                        self.current["deck"] = self.capturing_text.strip()
                elif self.capture_target == "date":
                    if self.current:
                        self.current["date"] = self.capturing_text.strip()
                self.capturing_text = ""
                self.capture_target = None
            elif self.in_time and tag == "time":
                self.in_time = False
    
    def handle_data(self, data):
        if self.in_article:
            text = data.strip()
            if text:
                if self.in_h2 or self.in_h3:
                    self.capturing_text += text + " "
                elif self.capture_target:
                    self.capturing_text += text
                elif self.in_time:
                    if self.current and not self.current.get("date"):
                        self.current["date"] = text


def parse_html_file(path):
    with open(path) as f:
        html = f.read()
    
    # Extract CDATA summary from each article link
    articles_data = []
    
    # Split by articles
    article_pattern = re.compile(r'<article[^>]*class="story-block[^"]*"[^>]*>(.*?)</article>', re.DOTALL)
    matches = article_pattern.findall(html)
    
    for blob in matches:
        item = {
            "href": "",
            "title": "",
            "deck": "",
            "date": "",
            "score": None,
            "excerpt": ""
        }
        
        # href
        m = re.search(r'<a[^>]+href="(/read/[^"]+)"', blob)
        if m:
            item["href"] = m.group(1)
        
        # title
        m = re.search(r'<h2[^>]*>(.*?)</h2>', blob, re.DOTALL)
        if not m:
            m = re.search(r'<h3[^>]*>(.*?)</h3>', blob, re.DOTALL)
        if m:
            item["title"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        
        # deck / subheading
        m = re.search(r'<p[^>]*class="story-block__deck[^"]*"[^>]*>(.*?)</p>', blob, re.DOTALL)
        if not m:
            m = re.search(r'<p[^>]*class="story-block__subheading[^"]*"[^>]*>(.*?)</p>', blob, re.DOTALL)
        if m:
            item["deck"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        
        # date
        m = re.search(r'<time[^>]*>(.*?)</time>', blob, re.DOTALL)
        if m:
            item["date"] = m.group(1).strip()
        else:
            m = re.search(r'<span[^>]*class="story-block__date[^"]*"[^>]*>(.*?)</span>', blob, re.DOTALL)
            if m:
                item["date"] = m.group(1).strip()
        
        # score
        m = re.search(r'(\d[\d.]*)\s*/\s*10', blob)
        if m:
            item["score"] = float(m.group(1))
        
        # excerpt - use deck
        item["excerpt"] = item["deck"][:500]
        
        articles_data.append(item)
    
    return articles_data


def build_records(articles_data):
    records = []
    seen = set()
    for art in articles_data:
        if not art["href"] or "/read/" not in art["href"]:
            continue
        
        url = art["href"] if art["href"].startswith("http") else f"https://mixmag.asia{art['href']}"
        
        if url in seen:
            continue
        seen.add(url)
        
        pub_date = parse_date(art["date"])
        
        album = art["title"]
        artist = art["deck"]
        
        record = {
            "album": album,
            "artist": artist,
            "score": art["score"],
            "url": url,
            "source": SOURCE,
            "pub_date": pub_date,
            "tags": [],
            "excerpt": art["excerpt"],
            "site_id": SITE_ID,
            "crawl_status": "ok",
            "type": "review",
        }
        
        # date filter
        if pub_date:
            try:
                pub = datetime.fromisoformat(pub_date)
                if pub < cutoff:
                    continue
            except Exception:
                pass
        
        # exclude filter
        text = album + art["excerpt"]
        if EXCLUDE_RE.search(text):
            print(f"  [exclude] {album[:60]}")
            continue
        
        records.append(record)
        print(f"  [+] {album[:60]}")
    
    return records


def main():
    html_file = WORKSPACE / "mixmag_asia_reviews_page.html"
    if not html_file.exists():
        print(f"ERROR: {html_file} not found")
        return
    
    print(f"Parsing {html_file}")
    articles_data = parse_html_file(html_file)
    print(f"Found {len(articles_data)} article blocks")
    
    records = build_records(articles_data)
    print(f"\nTotal: {len(records)}")
    
    with open(OUTPUT, "w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"Written: {OUTPUT}")


if __name__ == "__main__":
    main()