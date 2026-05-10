#!/usr/bin/env bash
# check-scraper-auth.sh — verify scraper profile auth.json is in a good state
# Part of: music-daily-recs skill

set -e

PROFILE_DIR="${HOME}/.hermes/profiles/scraper"
AUTH_JSON="${PROFILE_DIR}/auth.json"
SESSIONS_DIR="${PROFILE_DIR}/sessions"

echo "=== Scraper profile auth check ==="

if [[ ! -f "$AUTH_JSON" ]]; then
    echo "FAIL: $AUTH_JSON not found"
    exit 1
fi

# 1. Count providers — must be exactly 1
PROVIDER_COUNT=$(python3 -c "
import json, sys
with open('${AUTH_JSON}') as f:
    d = json.load(f)
cp = d.get('credential_pool', {})
print(len(cp))
" 2>/dev/null || echo "?")

echo "Provider count: $PROVIDER_COUNT (expect 1)"

if [[ "$PROVIDER_COUNT" != "1" ]]; then
    echo "WARN: credential_pool has $PROVIDER_COUNT entries — expected 1"
    python3 -c "
import json
with open('${AUTH_JSON}') as f:
    d = json.load(f)
for k, v in d.get('credential_pool', {}).items():
    print(f'  - {k}: {len(v)} entries')
"
fi

# 2. Check for wrong minimax.io endpoint
WRONG=$(grep -r "api.minimax.io" "${SESSIONS_DIR}/" 2>/dev/null | head -3 || true)
if [[ -n "$WRONG" ]]; then
    echo "FAIL: found wrong endpoint (api.minimax.io) in sessions:"
    echo "$WRONG"
    exit 1
fi

# 3. Check provider name
PROVIDER=$(python3 -c "
import json
with open('${AUTH_JSON}') as f:
    d = json.load(f)
cps = list(d.get('credential_pool', {}).keys())
print(cps[0] if cps else 'NONE')
" 2>/dev/null || echo "NONE")

echo "Provider: $PROVIDER (expect minimax-cn)"

if [[ "$PROVIDER" != "minimax-cn" ]]; then
    echo "WARN: expected provider 'minimax-cn', got '$PROVIDER'"
fi

# 4. Config check
CONFIG="${PROFILE_DIR}/config.yaml"
if [[ -f "$CONFIG" ]]; then
    PROVIDER_IN_CONFIG=$(grep -E "^\s*provider:" "${CONFIG}" | head -1 || true)
    echo "Config provider: ${PROVIDER_IN_CONFIG:-not set}"
fi

echo "=== Check complete ==="
