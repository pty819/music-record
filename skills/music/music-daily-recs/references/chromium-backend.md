# Chromium backend

The browser layer runs `bin/chromium_browser.py` (CDP client + a Camoufox-shaped
REST surface). No browser daemon, no `hermes-camoufox.service`.

**CDP mechanics and their pitfalls live in the `headless-browser-scraping` skill** —
the 403 handshake, the per-target domain split, the function-expression IIFE, and the
atexit cleanup are all documented there. This file only covers what is specific to
*this* pipeline.

## Interface

`bin/chromium_browser.py` exposes the same REST contract the old Camoufox service
did, so no scraper's DOM-extraction JS had to change:

```
POST   /tabs                {userId, sessionKey, url} -> {tabId}
POST   /tabs/{id}/navigate  {url}                      -> {success, tabId}
POST   /tabs/{id}/evaluate  {expression}               -> {result}
POST   /tabs/{id}/content   {}                         -> {html}
DELETE /tabs/{id}                                      -> {closed}
```

Three ways in:

| Way | Use |
|---|---|
| `from chromium_browser import LocalApiClient` | in-process — **what the scrapers use**; no port, no daemon |
| `python3 bin/chromium_browser.py --serve --port 9377` | HTTP mode for callers outside this repo |
| `fetch(url)` / `evaluate(url, js)` | one-off probes and diagnosis |

Self-check before blaming the browser layer:

```bash
python3 bin/chromium_browser.py --self-check
```

A scraper's `_api()` is now a one-liner; the contract is what makes the diff that small:

```python
def _api(method, path, body=None):
    return _CHROME.call(method, path, body)
```

## Migration state by delivery tier

"The grep is clean" and "the migration is done" are different claims. Split the roster,
because the two tiers have different blast radius:

| Tier | Scope | State |
|---|---|---|
| **Shipping** | all 17 entries of `scrape_html_parallel.py:SCRIPTS` | **complete** — zero callers reach the old endpoint |
| **Exploration** | `kanban-swarm.py:get_sites()` — 5 sites | **scripts not migrated**; separately, the worker body still names the Camoufox daemon |

Shipping detail — how each site got there:

| Site | Change |
|---|---|
| `musique_machine`, `all_about_jazz`, `mixmag_asia` | `_req`/`_api` body swapped for `LocalApiClient`; DOM JS untouched |
| `downbeat` | **fallback path only** — plain HTTP is still the primary; `fetch_camoufox()` became `fetch_chromium()` |
| other 13 | never referenced the daemon; no change needed |

Convert any straggler the same way: drop `CAMOFOX_BASE` / `CAMOFOX`, import
`LocalApiClient`, replace the `_api` / `_req` body, nothing else. Note the return
contracts are **not uniform** — some return `dict`, some `(status, body)` tuples — so
read each signature; a batch `sed` silently breaks the tuple-returning ones.

Verify with the shipping roster itself, not the whole tree:

```bash
sed -n '/^SCRIPTS = \[/,/^\]/p' bin/scrape_html_parallel.py | grep -c 9377   # expect 0
```

Repo-wide `grep -rn 9377 bin/` still hits — those are deliberate migration notes in
docstrings. Read each hit's context before concluding work is unfinished.

Migrating the exploration scripts is necessary but **not sufficient**: until
`build_scraper_body()` stops telling the worker to "Camoufox 浏览器访问列表页", the
workers still chase a daemon that does not exist. And that task body names no script
at all, which is why those site scrapers show as uncalled — a pre-existing condition,
not migration damage.

## Debugging a scraper that "hangs"

`all_about_jazz` looked like a CDP problem: `Runtime.evaluate` timed out. It was not.
Instrument the stages separately before touching the browser layer:

1. Does the listing page load? `document.readyState`, `document.title`, and the
   challenge marker (pitfall 5 in `headless-browser-scraping`).
2. Does the extraction JS run **on that page**? 16 cards came back in 0.1s — the
   JS and the site were both fine.
3. Only then look at the per-item loop. It calls `navigate` dozens of times, and a
   `navigate` implemented as `Target.createTarget` leaks one target per call until
   the CDP socket stalls.

The tell was the shape of the failure: the stage that timed out was *not* the stage
that was broken. Time each stage; the slow one and the buggy one are frequently
different stages.

## Silent OOM on this host

The 1.6GB host cannot hold an unbounded Chromium for a long scrape. When it fails, the
signature is deceptive: the job stops partway, **stderr has no traceback**, and the
output file is `0 bytes`. It reads as flaky rather than killed.

```bash
dmesg -T | grep "Killed process" | tail -3    # the only place the truth appears
```

Do not instrument the scraper — check the kernel log first. `chromium_browser.py`
caps the V8 old space from `MemAvailable` (1/4, clamped to [128, 512] MB) and passes
the launcher flags that keep renderer processes bounded; those are load-bearing on
this host, so raising concurrency or `max_runtime_seconds` makes it worse, not better.

After any memory change, prove the **trend** rather than a single clean run — one
success proves nothing when the old failure was probabilistic:

```bash
ps -eo rss,comm | grep -i chrome | awk '{s+=$1} END {print int(s/1024)\" MB\"}'
```

Sample across a dozen consecutive navigations and require it to oscillate and trend
flat or down, then confirm a job that previously died at item N now completes all N.

## Selector rot: a non-zero row count can still be all navigation

`mixmag_asia` returned 8 items, exit 0, no error — every "article" was a category
name (`Reviews`, `New Releases`, `Exclusive Mixes`). The selector
`a[href*="/music/"]` still matched after the site reorganised its URLs, but
`/music/` now only names section indexes; articles moved to `/feature/` and
`/read/`. This is pre-existing rot, invisible to any check that only counts rows.

Rules that caught it:

- Print the first few extracted titles and URLs. Section names are obvious; a row
  count is not evidence.
- When a section index and an article share a prefix, filter shallow paths:
  `new URL(url).pathname.split('/').filter(Boolean).length < 3`.
- Add the new article prefixes as their own selector branch rather than widening
  the old one — widening re-admits the nav.

## Per-site capability

Chromium replaces JS rendering. It does **not** replace an anti-detection fingerprint.

| Site | Verdict |
|---|---|
| musique_machine | works |
| point_of_departure | works |
| resident_advisor | works |
| **boomkat** | Cloudflare Turnstile — `document.title` comes back `"Just a moment..."` |

For boomkat, write 0 items per the empty-result protocol and exit early. Retrying the
browser against a challenge page never succeeds. Recovering it means changing the egress
IP (see `mihomo-proxy-management`), not changing browser.

## Running the pipeline on this host

`scrape_html_parallel.py` spawns each scraper as bare `python3`, so the venv must come
first on PATH or the subprocesses die with `ModuleNotFoundError: bs4` (and report a
failure that looks like a scraper bug):

```bash
export PATH=/home/liyifan/music-record/.venv/bin:$PATH
```

`chromium_browser.py` also needs `websocket-client`, which no system python here has.

## Operating cost

Chromium starts per scrape and exits when done — roughly 5-8s of startup per tab.
The upside is that the daemon, its systemd unit, and ~400MB of separate browser binary
are gone. Concurrency is now bounded only by `scrape_html_parallel.py`'s process
parallelism, no longer by browser instances.

## Scoring: never dodge an SDK signature change by pinning backwards

`provider_failover.py` passed `temperature=0.7` to `messages.create()`. The anthropic
SDK removed that parameter from the signature in 1.0, so every scoring call raised
`TypeError` and the day's report scored nothing.

The production host had an old SDK pinned, which is why it never surfaced there — the
bug only appears on a machine that installs current packages. Fix it by **deleting the
argument and testing against the newest SDK**, not by pinning the version that hides
the error.

Two things that bit on the way:

- The fake SDK in `tests/fakeanth/` declared `temperature` as a **required positional**,
  so removing it from the call site broke all 8 tests with a confusing `0 calls` instead
  of a useful `TypeError`. Test doubles must absorb signature changes with `**kwargs`.
- A stale `__pycache__` carried over from moving the repo kept pointing at the old
  absolute path and produced tracebacks into a directory that no longer existed. After
  relocating a checkout, delete `__pycache__` before trusting any failure output.
