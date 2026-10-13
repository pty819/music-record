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

# 6. Cron job status
hermes cronjob list | grep ec5ea562d589

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
