# Site Discovery & Style Analysis Reference

## Style Distribution Analysis Methodology

When analyzing what music styles the recommendation system covers, use this approach:

### Step 1: Extract Tags from Reports
```python
import re
from collections import Counter

# Read recent reports
reports = []
for date in ['2026-06-11', '2026-06-10', ...]:
    with open(f'recommend/{date}.md', 'r') as f:
        reports.append(f.read())

# Extract all tags
all_tags = []
for report in reports:
    tag_matches = re.findall(r'\*\*标签\*\*:\s*([^\n]+)', report)
    for match in tag_matches:
        tags = re.split(r'[,/\s]+', match.strip())
        all_tags.extend([t.strip().lower() for t in tags if t.strip()])
```

### Step 2: Categorize by Style Family
Define style categories to aggregate similar tags:
- **电子**: electronic, techno, house, ambient, dub, idm, glitch, synth, ebm, electro, drone
- **实验/前卫**: experimental, avant-garde, noise, extreme, improvisation
- **爵士**: jazz, free, fusion, improv, bebop
- **摇滚**: rock, progressive, prog, psych, krautrock
- **暗潮/哥特**: darkwave, goth, post-punk, coldwave, wave, industrial
- **世界音乐**: world, folk, roots, ethnic, global, asia, african, latin
- **古典/当代**: classical, modern, contemporary, composition

### Step 3: Count and Report
```python
tag_counter = Counter(all_tags)
sorted_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)
```

### Current Style Distribution (June 2026)
Based on 5 days of reports (1038 recommendations):
1. 电子音乐: 22.1%
2. 世界音乐: 11.9%
3. 摇滚: 10.6%
4. 实验/前卫: 9.6%
5. 暗潮/哥特: 7.2%
6. 爵士: 5.5%
7. 古典/当代: 4.1%
8. 工业: 4.0%

**Gap identified**: 噪音/工业音乐 coverage is relatively weak (4.0% industrial, minimal pure noise)

---

## Site Discovery Workflow

When looking for new media sources to enrich the review library:

### 1. Web Search Strategy
Use targeted queries:
- `"experimental music" review site OR blog OR magazine`
- `noise music blog industrial music review site`
- `avant-garde music review website`
- `dark ambient blog noise industrial`

### 2. RSS Feed Validation
Check common RSS paths for each candidate site:
```python
import requests
from urllib.parse import urljoin

def check_rss(base_url):
    rss_paths = ["/feed/", "/feed", "/rss/", "/rss", "/atom.xml", "/rss.xml"]
    for path in rss_paths:
        rss_url = urljoin(base_url, path)
        try:
            response = requests.get(rss_url, timeout=5)
            if response.status_code == 200 and 'xml' in response.headers.get('content-type', ''):
                return rss_url
        except:
            continue
    return None
```

### 3. Site Evaluation Criteria
- **Update frequency**: Daily/weekly updates preferred
- **Review depth**: Full album reviews > brief mentions
- **Style focus**: Should fill gaps in current coverage
- **RSS availability**: Must have working RSS feed for automation
- **Domain authority**: Higher DA = more reliable source

---

## Sites Added (June 2026)

After validation, 6 sites were added to the pipeline. 4 sites were rejected due to low update frequency or RSS issues.

### Added Sites

| Site | URL | RSS | Focus | Update Freq | Gap Filled |
|------|-----|-----|-------|-------------|------------|
| Noise Not Music | noisenotmusic.com | /feed/ | experimental, avant-garde, noise | 0.7/week | 噪音音乐 |
| The Noise Beneath The Snow | thenoisebeneaththesnow.wordpress.com | /feed/ | noise, gothic, industrial, metal, dark ambient | 1.0/week | 哥特/新民谣 |
| Can This Even Be Called Music? | canthisevenbecalledmusic.com | /feed/ | experimental, underground | 1.3/week | 地下音乐 |
| The Elite Extremophile | theeliteextremophile.com | /feed/ | progressive, experimental | 1.1/week | 前卫摇滚 |
| Heavy Blog Is Heavy | heavyblogisheavy.com | /feed/ | progressive, experimental, avant-garde metal | 7.5/week | 前卫金属 |
| Record Crates United | recordcratesunited.com | /feed/ | experimental, underground, cult | 1.9/week | cult音乐 |

### Rejected Sites (with reasons)

| Site | Reason |
|------|--------|
| This Is Darkness | Update frequency too low (0.2 posts/week) |
| The Road to Sound | Last updated November 2025 |
| Dungeon Synth & Dark Ambient Reviews | Last updated October 2024 |
| Louder Than War | RSS timeout, couldn't verify |

### Site Onboarding Checklist
1. ✅ Verify RSS feed works (HTTP 200 + valid XML)
2. ✅ Check update frequency (target: ≥ 0.5 posts/week)
3. ✅ Confirm review format (album reviews, not just news/playlists)
4. ✅ Add to `data/sites.json` with proper tags
5. ✅ Add to `bin/fast-rss-scrape.py` TAG_MAP
6. ✅ Update SKILL.md site list and counts
7. ✅ Git commit and push
8. ✅ Monitor first few runs for quality

---

## Pitfalls

- **RSS feed URLs vary**: Some use `/feed/`, others `/rss`, `/atom.xml`. Always check multiple paths.
- **WordPress sites**: Common pattern is `/feed/` endpoint
- **Content type validation**: Check response contains XML, not just 200 status
- **Update frequency matters**: Sites with < 0.5 posts/week may not be worth adding. Check the date range of recent entries.
- **RSS timeout = skip**: If RSS feed times out (> 30s), skip the site rather than trying to force it
- **Style tags inconsistency**: Different sites use different tag vocabularies. Normalize before counting.
- **TAG_MAP update required**: When adding RSS sites, must also add to `bin/fast-rss-scrape.py` TAG_MAP
- **SKILL.md counts must match**: Update all references to site counts in SKILL.md (description, architecture diagram, site list header)
- **Check content type**: Some "review" sites mainly publish news/playlists, not album reviews. Verify the site actually publishes reviews before adding.

---

## Related Skills
- `blogwatcher` - For monitoring RSS feeds (different purpose: ongoing monitoring vs. one-time discovery)
- `research` - General research methodology (too broad for this specific task)
