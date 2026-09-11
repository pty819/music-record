# Point of Departure — Feature Article Album Name Issue

## Symptom

Daily recommendations show `### 未知专辑` (Unknown Album) for Point of Departure items sourced from feature/column/interview pages (PageOne, Hanes, Henkin, Ezz-thetics), while Moment's Notice review items display correct album names.

## Root Cause

Point of Departure has two layout families:

1. **Review pages** (MomentsNotice.html, MoreMoments2.html): Use `<em>Artist<br><strong>Album</strong><br>Label</em>` header — correctly parsed → `album`/`artist` populated ✓
2. **Feature pages** (PageOne, Hanes, Henkin, Ezz-thetics): Columns/interviews with no `<em>Artist<strong>Album</strong>Label</em>` header. The article title lives in a `<strong>` paragraph but `parse_feature_page()` never extracted it.

Three page layouts exist:

| Type | P0 | P1 | P2 | Example |
|------|----|----|----|---------|
| A: col-name → byline → title | `<strong>Page One</strong>` (short) | byline | `<strong>Matthew Wright: ...</strong>` (title) | PageOne, Henkin |
| B: title-as-P0 → byline | `<strong>Simon Hanes: ...</strong>` (long, >25ch) | byline | body | Hanes |
| C: col-name → byline → body | `<strong>Ezz-thetics</strong>` (short) | byline | body (no article title) | Ezz-thetics |

## Fix (2026-06-26, commit 282a2b2)

Two files changed:

### `bin/scrape_point_of_departure.py` — `parse_feature_page()`

1. **P0 sniffing**: Before the loop, check if P0 has `<strong>` and text > 25 chars. If so, it's a Hanes-style article title, not a column name — don't skip it.
2. **Title extraction**: Scan for the first `<strong>` paragraph (not column name, not byline) with text < 120 chars. Use it as `album`.
3. **HTML entity decoding**: `html_mod.unescape()` on the extracted title (handles `&amp;` → `&`).

New return value includes `album: article_title` instead of `album: ""`.

```python
# Key heuristic
_p0_is_long_title = False
if paragraphs and "<strong" in paragraphs[0].get("html", "").lower():
    _p0_is_long_title = len(paragraphs[0].get("text", "")) > 25

# Title detection
if not article_title and "<strong" in html.lower() and len(text) < 120:
    article_title = re.sub(r"<[^>]+>", "", html).strip()
    article_title = html_mod.unescape(article_title)
    continue
```

### `bin/generate_report.py` — `generate_markdown()`

Fallback for items that still have no title (Ezz-thetics pattern):

```python
if album == "未知专辑":
    excerpt = item.get("excerpt", "") or item.get("body", "") or ""
    first_line = excerpt.split("\n")[0].strip()[:80]
    if first_line:
        album = first_line
```

## Results

| Page | Before | After |
|------|--------|-------|
| PoD95PageOne.html | `### 未知专辑` | `### Matthew Wright: Notation, Improvisation, and Technology` |
| PoD95Hanes.html | `### 未知专辑` | `### Simon Hanes: Transgressive Obsession` |
| PoD95Henkin.html | `### 未知专辑` | `### Miles & Trane` |
| PoD95Ezz-thetics.html | `### 未知专辑` | `### The previous Ezz-thetics column reflected...` (excerpt fallback) |

## Code Locations

| File | Function | What |
|------|----------|------|
| `bin/scrape_point_of_departure.py` | `parse_feature_page()` | Article title extraction + P0 sniffing |
| `bin/scrape_point_of_departure.py` | `build_item()` | Schema (no field change needed) |
| `bin/generate_report.py` | `generate_markdown()` ~line 62 | Album fallback from excerpt first line |
