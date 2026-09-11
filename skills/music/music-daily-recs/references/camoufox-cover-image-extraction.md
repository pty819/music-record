# Camoufox Cover Image Extraction Debugging

## The Problem

Point of Departure (PoD) reviews have album artwork embedded as `<img>` tags inside review pages, but the scraper never extracts them. The output JSON has no `cover_url` field.

## Root Cause — 3 Layers of Failure

### Layer 1: PAGE_JS only queries `<p>` elements

The JavaScript expression (`PAGE_JS`) that runs inside the browser to extract page content uses:

```javascript
const ps = document.querySelectorAll('p');
```

This only captures paragraphs. An `<img>` tag inside a `<p>` has `innerText=""` (images carry no text). So the image shows up as a paragraph with empty text and `html: "<img src=\"...\">"`.

### Layer 2: Parsing functions discard or ignore images

Two different behaviors depending on the page type:

**Single-review page** (`parse_single_review_page`, `PoD95MomentsNotice.html`):

```python
# Line 441-444 — explicitly skips image paragraphs
if html.lstrip().startswith("<img"):
    continue  # ← image silently dropped
```

**Multi-review aggregator page** (`parse_aggregator_page`, `PoD95MoreMoments2.html`):

```python
# Line 316-321 — saves raw HTML but never parses src
if html.lstrip().startswith("<img"):
    current.append({"html": html, "text": text, ...})
    continue
```

The aggregator page keeps the raw `<img>` HTML in the chunk data, but the `build_item()` function never reads it. So it's saved but never used.

### Layer 3: `build_item` has no image field

The output dict for every review:

```python
return {
    "album": album,
    "artist": artist,
    "score": None,
    "url": url,
    ...
    # ← no cover_url / image field exists
}
```

The schema was designed for text-only output.

## Image URL Pattern

From crawling the actual pages:

| Page | Images found | Pattern |
|------|-------------|---------|
| `PoD95MomentsNotice.html` | 5 `<img>` tags | `img/95_Lead_Review_Cover.jpg` (cover), `img/95_Lead_Review_Photo.jpg` (photo), `img/95_AD_Intakt_Large.jpg` (ad) |
| `PoD95MoreMoments2.html` | 9 `<img>` tags | `img/95_MN_Ahmed_Cover.jpg` (cover), `img/95_MN_Sylvie_Courvoisier_Cover.jpg` (cover)... + `img/95_AD_AlAy_Large.jpg` (ad) |

Absolute URLs resolve to:
```
https://pointofdeparture.org/PoD95/img/95_MN_Ahmed_Cover.jpg
```

Image types by URL pattern:
- `*_Cover.jpg` / `*_Cover_*.jpg` — album cover art (what we want)
- `*_Photo.jpg` — artist photo
- `*_AD_*` — advertisement, NOT album art
- `*_Lead_Review_*` — lead review image

## Fix Pattern

Three things need changing in `scrape_point_of_departure.py`:

### 1. PAGE_JS: Add image extraction

Add alongside the paragraph query:

```javascript
const imgs = document.querySelectorAll('img');
const imgData = [];
for (const img of imgs) {
    const src = img.getAttribute('src') || '';
    if (src) {
        imgData.push({
            src: src,
            alt: img.getAttribute('alt') || '',
            absUrl: new URL(src, location.href).href
        });
    }
}
```

Return `imgData` alongside `paragraphs`.

### 2. Parsing: Extract src from image paragraphs

In both `parse_single_review_page` and `parse_aggregator_page`:

```python
import re
# Extract first <img src="..."> from html
m = re.search(r'<img[^>]+src="([^"]*)"', html, re.I)
if m:
    cover_url = normalize_href(m.group(1))
```

Store `cover_url` in the review dict instead of dropping the paragraph.

### 3. build_item: Add cover_url field

```python
return {
    ...
    "cover_url": cover_url,  # new field
}
```

### Distinguishing covers from ads

Not all images on a page are album covers. Ad images can be identified by URL pattern:
- Contains `_AD_` or `_AD_` → advertisement, skip
- Everything else → likely album art or artist photo

The lead review on `PoD95MomentsNotice.html` has two images: a cover (`95_Lead_Review_Cover.jpg`) and a photo (`95_Lead_Review_Photo.jpg`). Both are contextual. For the aggregator pages, each review chunk typically has exactly one cover image.

## Verification

After fixing, check:
1. `cover_url` exists in output items
2. URL resolves: `curl -s -o /dev/null -w "%{http_code}" "https://pointofdeparture.org/PoD95/img/95_MN_Ahmed_Cover.jpg"` → 200
3. No ad images (containing `_AD_`) got mixed in as covers
