# 2026-06-14 Site Count Drift Detection & Correction

## Problem
SKILL.md had stale site counts that didn't match `data/sites.json`:
- RSS: said 34 (or 29 in some versions) → actual 50
- HTML: said 17 → actual 18
- Camoufox: said 4 → actual 6 (added jazztokyo, musicircus)

## Root Cause
`data/sites.json` evolves as new sites are added, but SKILL.md section headers
and architecture diagram are manually maintained and drift over time.

## Detection
During cron execution, `kanban-swarm.py --confirm` output showed 6 active Camoufox
sites instead of the 4 listed in SKILL.md. The RSS scraper also scanned 50 sites
(not 34/29).

## Fix (v7.8)
Updated SKILL.md to reflect actual counts:
- Summary line: 75 站 = 50 RSS + 18 HTML + 6 Camoufox + 1 skip
- Architecture diagram: 6 Camoufox workers
- Section headers: 50 RSS, 18 HTML, 6 Camoufox
- Step descriptions: 50 站, 18 站

## Prevention
After any `sites.json` update (adding/removing sites), the SKILL.md should be
updated in the same commit. The section headers are the most commonly missed.

## Verification
```bash
cd /home/liyifan/music-record
python3 -c "
import json
sites = json.load(open('data/sites.json'))
rss = len([s for s in sites if s.get('has_rss') and s.get('rss_url')])
html = len([s for s in sites if s.get('layer') == 'html'])
camo = len([s for s in sites if s.get('layer') == 'camoufox'])
skip = len([s for s in sites if s.get('layer') == 'skip'])
print(f'RSS={rss} HTML={html} Camoufox={camo} Skip={skip} Total={rss+html+camo+skip}')
"
```
