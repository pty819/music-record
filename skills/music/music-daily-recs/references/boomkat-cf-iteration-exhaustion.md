# Boomkat CF / Iteration Budget Exhaustion — Root Cause & Fix

## Incident (2026-06-11)

Boomkat worker (t_ada9a353) crashed twice with `pid not alive`.  
Wild City worker (t_86d22857) timed out with `Iteration budget exhausted (90/90)`.

Both workers ended as `blocked`, blocking Verifier + Synthesizer.

## Root Cause

**Boomkat**: Cloudflare Turnstile challenge triggers on every new tab. LLM worker遇到 CF 后，花全部 90 iterations 写 probe 脚本调试（`probe_challenge_html.py`, `probe_ts.py`, 多轮 `curl /tabs/evaluate`）→ 从不到达 `kanban_complete()` → iteration 耗尽 → `blocked`。

**Wild City**: `scrape_wild_city.py` Phase 4 逐个 URL navigate + evaluate，每个产品 ~2-4 次 API 调用。100+ reviews × 3 calls = 300+ iterations → 90 budget 全烧。

Both share the same pattern: **LLM tries to solve the problem instead of cutting losses**.

## Fix Applied

### 1. Boomkat — CF Early Exit (kanban-swarm.py)

Added `BOOMKAT_EARLY_EXIT` template block in `build_scraper_body()` (sid == "boomkat"):

```
创建 tab → 等 15s → JS 检查:
  document.title + '|' + document.querySelectorAll('.listing2__product').length
  → title 含 "Just a moment" 或 products==0
  → 立即写入 {"meta":{"total":0,"cf_blocked":true},"items":[]}
  → kanban_complete(summary="boomkat CF blocked, 0 items", metadata={...})
  → STOP，不要开新 tab，不要重试
```

Key principle: **CF challenge = terminal state for this IP/ASN. Don't retry within the same run.**

### 2. Wild City — max-items cap (scrape_wild_city.py)

Added `--max-items 20` argument. Phase 4 loop:
```python
url_list = list(all_reviews.items())[:max_items]
```
Reduces iterations from 300+ → ~60 for a full run.

## Pattern for Future Camoufox Workers

When designing a worker body for sites with known obstacles:

1. **Identify the failure mode** (CF challenge, pagination explosion, repeated nav)
2. **Insert an early exit checkpoint** BEFORE the main loop:
   - Probe once after initial load
   - If obstacle detected → `kanban_complete([])` immediately
3. **Cap iteration-heavy loops** with `--max-items N`
4. **Write the rule in the body constraints**, not just the preamble:
   - `禁止：CF 拦截后继续开新 tab 重试（直接用早期退出）`

## Verification

After fix, check:
```bash
hermes kanban list | grep "$(date +%Y-%m-%d)"
# boomkat should be "done" not "blocked"
# wild_city should be "done" not "blocked"
```