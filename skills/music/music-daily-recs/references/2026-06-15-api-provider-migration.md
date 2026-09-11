# 2026-06-15 API Provider Migration: Tencent Cloud hy3 → MiniMax M3

## Final State

`process_reviews.py` switched from Tencent Cloud's Anthropic-compatible endpoint to MiniMax China's Anthropic-compatible endpoint. SDK stayed as `anthropic`.

| Item | Before | After |
|------|--------|-------|
| SDK | `anthropic` | `anthropic` (unchanged) |
| Base URL | `https://api.lkeap.cloud.tencent.com/plan/anthropic` | `https://api.minimaxi.com/anthropic` |
| Model | `hy3-preview` | `MiniMax-M3` |
| API key file | `~/.config/music-recs/minimax_key` | `~/.config/music-recs/minimax_cn_key` |
| API key env var | `MINIMAX_CN_API_KEY` (same) | `MINIMAX_CN_API_KEY` (same) |
| Response format | Anthropic (`message.content[].text`) | Anthropic (same) |

## What Was Changed in Code

Three lines in the config section:
```python
BASE_URL = "https://api.minimaxi.com/anthropic"  # was: api.lkeap.cloud.tencent.com/plan/anthropic
MODEL = "MiniMax-M3"                               # was: hy3-preview
_API_KEY_PATH = "...minimax_cn_key"                # was: minimax_key
```

Everything else (client init, response parsing, ThinkingBlock skip, JSON strategies) stayed identical.

## MiniMax Anthropic-Compatible Endpoint

- 国内: `https://api.minimaxi.com/anthropic`
- 国际: `https://api.minimax.io/anthropic`
- Anthropic SDK auto-appends `/v1/messages` to base URL
- Model name: `MiniMax-M3` (also `MiniMax-M2.7`, `MiniMax-M2.5` etc.)
- Works with `anthropic.Anthropic` client directly, no SDK change needed

## Why

User's preference: use MiniMax China (already has API key for MCP/TTS) instead of maintaining a separate Tencent Cloud account.

## Naming Note

User referred to the Tencent Cloud endpoint as "TokenHub". This is not an official name — the actual service is Tencent Cloud LKEAP (大模型引擎). If a user says "TokenHub", they mean the scoring API endpoint in `process_reviews.py`.

## Rollback
If MiniMax M3 has issues, revert three config lines to use Tencent Cloud endpoint. Old key file was at `~/.config/music-recs/minimax_key` (deleted during migration; restore from backup if needed).
