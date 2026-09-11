# 2026-08-16 Provider Failover 多模型容错

## 背景

2026-08-16 凌晨 04:25，音乐推荐 cron 的评分环节全部失败：
- MiniMax-M3（评分唯一依赖的 provider）返回 429 错误 2056「已达到 Token Plan 用量上限」
- 0/228 条评分成功 → synthesizer 停手（不推空报告）→ 当天无推荐、无推送

排查发现这**不是首次**——MiniMax CN Token Plan（`sk-cp-` 前缀，订阅制）在凌晨时段会周期性触顶（记忆里已有"M3 凌晨并发突发"规律）。

## 根因

评分管道单点依赖一个 provider：
```
scraped_raw.json → process_reviews.py → [MiniMax-M3] → processed.json
                                        ↑ 单点，挂了全挂
```

## 方案

新增 `bin/provider_failover.py` 多 provider 容错层：

```
scraped_raw.json → process_reviews.py → provider_failover.py → [MiniMax-M3 (主)]
                                                               [Ark DeepSeek-v4 (备)]
```

### Provider 定义

| # | 名称 | 端点 | 模型 | key |
|---|---|---|---|---|
| 0 | MiniMax（主） | `api.minimaxi.com/anthropic` | MiniMax-M3 | `~/.config/music-recs/minimax_cn_key` |
| 1 | Ark（备） | `ark.cn-beijing.volces.com/api/coding/v1` | deepseek-v4-flash-ga-260731 | `HERMES_CUSTOM_ARK_CN_BEIJING_VOLCES_COM_API_KEY` |

### 容错逻辑

- 单条失败重试 2 次（指数退避）→ 仍失败切换下一个 provider
- 配额/429 类错误（2056 / 用量上限 / quota / rate limit）→ **立即切换不重试**
- 所有 provider 都失败 → 该条记 fail（0 分，由低分清理机制兜底）
- 切换记录写进 `processed.json` 的 `meta.provider_stats` / `meta.provider_switch_log`

### 关键实现细节

- Ark 用 OpenAI 兼容协议（urllib），MiniMax 用 Anthropic 兼容协议（anthropic SDK），`_call` 按 `api_mode` 分发
- `_extract_json` 复用 process_reviews 的三策略（直接解析 → markdown 代码块 → 正则找 total_score）
- DeepSeek 可能返回 `reasoning_content`（thinking），提取时取 `message.content` 即可
- Ark key 在 `~/.hermes/.env` 里（`HERMES_CUSTOM_ARK_CN_BEIJING_VOLCES_COM_API_KEY`），**config.yaml 里那个 `ark-1984...` 是过期的会报 AuthenticationError**，别用它

## 验证

### 单元测试（模拟故障切换）

```
场景1: MiniMax 正常 → 全程主 provider ✅
场景2: MiniMax 故障(base_url 指向 127.0.0.1:1) → 自动切 Ark 评分成功 ✅
场景3: Ark 直连正常 ✅
```

### 集成测试（真实数据子集）

取 scraped_raw 前 8 条跑 process_reviews：
- 8/8 评分成功，全程 MiniMax（正常态）
- Provider 统计正确写入 meta：`{"minimax": {"ok": 8, "fail": 0}, "ark": {"ok": 0, "fail": 0}}`

### 自检命令

```bash
python3 bin/provider_failover.py --self-check
# 期望两个 provider 都返回 ✅ 可用
```

## 踩坑

1. **`while` 循环残留 `tried += 1` 重复计数**：patch 重构时把旧的「配额错误 break」残留代码（`tried += 1; idx = (idx+1)%2`）留着没删，导致切换后 `tried` 被加两次 → `while tried < len(PROVIDERS)` 提前退出 → Ark 根本没轮到。症状：`switch_log` 显示已切 Ark，但 `ark.fail=0`（从未被调用）、返回 all-failed。**修复**：删除残留的重复 `tried += 1`。

2. **config.yaml 里 Ark key 已过期**：`ark-19842ed1-...` 探测返回 `AuthenticationError`。有效的 key 在环境变量 / `~/.hermes/.env`（`HERMES_CUSTOM_ARK_CN_BEIJING_VOLCES_COM_API_KEY` = `ark-5980...`）。改代码时不要从 config.yaml 读 key。

## 后续

- 如果 Ark 也出现 429：考虑加第三个 provider（如 z.ai GLM）或把 MiniMax 套餐从 Token Plan 升级到按量
- 监控 `processed.json` 的 `meta.provider_stats`，连续多日 `ark.ok > 0` 说明 MiniMax 频繁触顶，值得升级套餐
