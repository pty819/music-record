# Gateway/Cron Outage — Diagnosis Reference

**Two failure modes, same symptom: cron misses its trigger.**

## Mode A: Server Reboot (most common)

The entire machine goes down → gateway process disappears → cron cannot fire.

**How to identify:**
- `gateway.log` shows `Received SIGTERM/SIGINT — initiating shutdown` right before the gap (SIGTERM = OS sending shutdown signal to all processes before reboot)
- `mcp-stderr.log` has a long gap with no `starting MCP server` entries, then a sudden burst when the server comes back
- `journalctl --user -u hermes-gateway` shows systemd restart times
- `last reboot` shows the machine was down
- Gateway PID changes after restart

**Timeline example (2026-05-12, server kernel compile):**
| Time (Beijing) | Event |
|---|---|
| 05-11 ~16:42 | Server rebooted (kernel build finished?) → gateway receives SIGTERM, shuts down gracefully |
| 05-11 16:44–17:06 | Gateway attempts restart multiple times but server is still unstable |
| 05-11 17:06+ | Server fully down or gateway stopped responding |
| 05-12 04:00 | **Cron trigger fires — gateway offline, job missed** |
| 05-12 05:22 | Server comes back up, gateway restarts with fresh PID |

**Recovery:** Manual backfill of the missed day's pipeline.

## Mode B: Gateway Process Crash Loop

Gateway process exits unexpectedly (crash), but server stays up.

**How to identify:**
- `mcp-stderr.log` shows dense cluster of `starting MCP server 'MiniMax'` entries in short succession
- `gateway-exit-diag.log` has `SystemExit: 75` traceback (APScheduler crashed, runner exits with code 75)
- Often triggered by Telegram reconnect storms (network flapping causes repeated disconnects)
- No `Cron ticker stopped` in `gateway.log` — crash-exit bypasses shutdown handler
- APScheduler logs show multiple `Scheduler started` in rapid succession

## Mode C: Profile Reservation Conflict Crash Loop (multi-unit gateway)

The gateway reserves the profiles it serves. A **second** systemd user unit for
one of those profiles (e.g. `hermes-gateway-<profile>.service` started by an
ad-hoc script) makes both processes fight over the same reservation; the loser
exits at startup with:

```
ERROR gateway.run: Cannot reserve gateway profiles: Gateway runtime already owns profile ...
```

With `Restart=always` + `RestartSec=5` this becomes an endless exit-1 loop —
the gateway restarts every ~20s and never stays up, so the cron trigger that
falls inside the window never runs:

```
GatewayUnavailableError: Gateway starting: deadline
```

**Tells:** systemd restart counter in the thousands over a few hours; journal
shows `⚠ This gateway is STANDALONE: it serves only its own profile` for the
offending unit; `/root/.hermes/profiles/<name>/gateway.lock` names the other
PID as owner.

**Fix:** one gateway unit per host. Stop/disable the per-profile unit, keep the
host unit (it already multiplexes all profiles when
`gateway.multiplex_profiles: true`), delete the ad-hoc switch scripts, and
ensure the host unit is enabled *and* linked into
`/root/.config/systemd/user/default.target.wants/` (a `disabled` unit missing
that symlink never comes back after a reboot — cron then silently stops for
good). Full read-only diagnosis: the `hermes-gateway-operations` skill's
`references/gateway-unit-conflicts.md`.

## Diagnostic Commands

```bash
# 1. Did the server reboot? (check FIRST)
last reboot | head -5
uptime

# 2. systemd restart timeline
journalctl --user -u hermes-gateway --no-pager 2>/dev/null | grep -E "Started|Stopped|restart" | tail -20

# 3. Gateway restart frequency (dense restarts = crash loop; long gap = server down)
tail -200 ~/.hermes/logs/mcp-stderr.log | grep "starting MCP server"

# 4. APScheduler state (no shutdown = crash; shutdown present = graceful stop)
grep "Scheduler started\|apscheduler shut down" ~/.hermes/logs/agent.log | tail -10

# 5. Cron ticker state
grep "Cron ticker" ~/.hermes/logs/gateway.log | tail -5

# 6. Cron job status (verified command path)
hermes cron doctor
# or query the ledger directly (the CLI spelling has changed across versions):
python3 -c "
import sqlite3
db=sqlite3.connect('file:/root/.hermes/cron/executions.db?mode=ro',uri=True); db.row_factory=sqlite3.Row
for r in db.execute('SELECT job_id,status,started_at,finished_at,error FROM executions ORDER BY started_at DESC LIMIT 5'):
    print(dict(r))"

# 7. Gateway exit records (SystemExit 75 = crash exit)
cat ~/.hermes/logs/gateway-exit-diag.log | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        if 'SystemExit' in d.get('msg','') or d.get('code') == 75:
            print(d['time'], d.get('msg',''), 'code:', d.get('code'))
    except: pass
"
```

## Mitigation

**Short-term:** Monitor server uptime. If server must reboot, cron will miss triggers during downtime — backfill manually.

**Long-term:** Move cron scheduler out of gateway process (planned `cron_mode: external`). Gateway crash or server reboot would no longer affect scheduling.
