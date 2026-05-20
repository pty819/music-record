import feedparser
from datetime import datetime, timezone, timedelta
import re
import json
import html

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", "\"")
    text = text.replace("&#39;", "'")
    return " ".join(text.split()).strip()

feed = feedparser.parse("https://www.freejazzblog.org/feeds/posts/default?alt=rss")

now = datetime(2026, 5, 20, tzinfo=timezone.utc)
three_days_ago = now - timedelta(days=3)

items = []
for entry in feed.entries:
    pub_str = entry.get("published", "")
    try:
        pub_date = datetime.strptime(pub_str, "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc)
    except:
        try:
            pub_date = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        except:
            pub_date = None

    if pub_date is None or pub_date < three_days_ago:
        continue
    if pub_date > now:
        continue

    title = entry.title
    link = entry.link

    # Parse album/artist from title: "Artist - Album (Label, Year)"
    # Some titles like "Negotiating Control and Openness: Three Albums by X" have no dash
    if " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        album = parts[1].strip()
    elif ": " in title:
        # "Album Title: Subtitle by Artist" or "Album Title: by Artist"
        parts = title.split(": ", 1)
        album = parts[0].strip()
        artist_part = parts[1].strip() if len(parts) > 1 else ""
        # Check if artist part starts with "by " -> then artist is the rest after "by"
        by_match = re.search(r"\bby\s+(.+)", artist_part, re.IGNORECASE)
        if by_match:
            artist = by_match.group(1).strip()
        else:
            artist = artist_part
        # If artist contains label/year pattern, strip it
        artist = re.sub(r"\s*\([^)]{1,50}\)\s*$", "", artist).strip()
    else:
        artist = ""
        album = title.strip()

    # Remove (Label, Year) or similar from album
    album = re.sub(r"\s*\([^)]*\d{4}[^)]*\)\s*$", "", album).strip()
    album = re.sub(r"\s*\([^)]{1,40}\)\s*$", "", album).strip()

    # Description
    description = entry.get("summary", "") or entry.get("description", "")
    plain_desc = strip_html(description)

    # Score extraction - look for explicit star ratings like **** or *****
    # Must be surrounded by whitespace/punctuation, not letters/digits, min 2 stars
    score = None
    star_match = re.search(r"(?<![a-zA-Z0-9])(\*{2,5})(?![a-zA-Z0-9*])", plain_desc)
    if star_match:
        score = len(star_match.group(1))

    # Excerpt - first 500 chars
    excerpt = plain_desc[:500].strip()
    if len(plain_desc) > 500:
        excerpt += "..."

    # Tags - entry.tags is a list of Tag objects (feedparser)
    tags = []
    if hasattr(entry, 'tags'):
        for t in entry.tags:
            if isinstance(t, dict):
                tags.append(t.get('term', '').strip())
            elif hasattr(t, 'term'):
                tags.append(t.term.strip())

    # Determine type - features are roundups, interviews, top lists, etc.
    # Titles like "Three Albums by X" are roundups/features, not single album reviews
    type_ = "review"
    title_lower = title.lower()
    non_review_indicators = ["three albums", "roundup", "top 10", "top 20", "weekend",
                             "interview", "portrait", "deep dive", "album of the year",
                             "best of", "hot list", "essentials", "video premiere",
                             "sunday video", "sunday interview"]
    if any(ind in title_lower for ind in non_review_indicators):
        type_ = "feature"

    # Also check tags for feature indicators
    for tag in tags:
        if any(nr in tag.lower() for nr in ["feature", "interview", "roundup", "top 10",
                                             "sunday interview", "portrait", "deep dive",
                                             "album of the year"]):
            type_ = "feature"
            break

    # Non-music filter
    non_music = ["blu-ray", "blu ray", "uhd", "vod", "dvd"]
    text_to_check = (album + " " + artist).lower()
    if any(nm in text_to_check for nm in non_music):
        print(f"SKIP non-music: {title}")
        continue

    # Reviewer name - try to extract from description
    reviewer_match = re.search(r"By\s+([A-Z][a-zA-Z\s]+?)(?:\s*$|\s*\n)", plain_desc)
    reviewer = reviewer_match.group(1).strip() if reviewer_match else ""

    item = {
        "album": album,
        "artist": artist,
        "score": score,
        "url": link,
        "source": "Free Jazz Blog",
        "pub_date": pub_date.isoformat(),
        "tags": tags,
        "excerpt": excerpt,
        "site_id": "free_jazz_blog",
        "crawl_status": "success",
        "type": type_
    }
    items.append(item)
    print(f"ADDED [{type_}]: {title[:70]}")
    print(f"  album={album[:40]}, artist={artist[:30]}, pub={pub_date.date()}")

print(f"\nTotal items: {len(items)}")

# Write output
with open("/home/liyifan/music-record/2026/05/2026-05-20/free_jazz_blog_reviews.json", "w") as f:
    json.dump(items, f, indent=2, ensure_ascii=False)

print("Written to free_jazz_blog_reviews.json")
