# 2026-10-09 火山 Ark 备 provider 订阅过期，已删除

## 症状

`processed.json` 的 `meta.provider_stats` 里 `ark.ok` 连续多日为 0，
但 `ark.fail` 每天 9~60 次。`provider_switch_log` 刷屏：

```
[07:06:27] 切换到 MiniMax-M3: Ark DeepSeek-v4-flash 重试2次仍失败: HTTP Error 400: Bad Request
```

`minimax.fail` 也同步偏高（35~68/天），因为切过去再切回来被重复计一次 fail。

## 根因

**不是代码 bug，是订阅状态失效。** 裸 HTTP 400 看不到原因，必须打响应体：

```bash
curl -s -X POST https://ark.cn-beijing.volces.com/api/coding/v1/chat/completions \
  -H "Authorization: Bearer $ARK_KEY" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash-ga-260731","max_tokens":64,
       "messages":[{"role":"user","content":"回复 OK 两个字母即可"}]}'
```

```json
{"error":{"code":"InvalidSubscription",
 "message":"Your account (...) does not have a valid CodingPlan subscription,
            or your subscription has expired."}}
```

`--self-check` 只打印 `str(e)[:120]`（= `HTTP Error 400: Bad Request`），
**看不到 error body**，所以这个故障能潜伏六天没人发现。

## 关键教训

1. **key 存在 ≠ 端点可用。** `_ark_key()` 一直正常返回 key（46 字符 `ark-5980...`），
   `self_check` 里 `key=有 ✅ 可用` 也照样打印 —— 它只判断 key 非空。
   唯一可靠的自检是**真实发一次请求并读 error body**。
2. **`InvalidSubscription` 不是配额类错误。** `_is_quota_error()` 的信号列表
   （2056/quota/429/...）不包含它 → 走"重试 2 次再切下一个"的路径，
   而下一个就是唯一的主 provider → 死循环。订阅类错误应该直接
   `enabled=False` 或让 provider 永久下线，而不是重试。
3. **熔断会掩盖真实故障。** 切换日志刷得很热闹（看起来"在容错"），
   实际上第二个 provider 从未成功过一次。判断容错是否有效要看
   `provider_stats.<name>.ok`，不是看 switch_log 有没有输出。

## 排查手法

```python
# 一天一个文件，按 provider 统计 ok/fail，快速看出哪个是真挂了
import json, pathlib
for p in sorted(pathlib.Path("2026").rglob("processed.json"),
                key=lambda x: x.stat().st_mtime, reverse=True)[:7]:
    m = json.loads(p.read_text(encoding="utf-8"))["meta"]
    print(p.parent.name, m.get("provider_stats"))
```

## 修复

`PROVIDERS` 移除 ark 条目；`_provider_stats` 改为按 PROVIDERS 推导
（`{p["name"]: {...} for p in PROVIDERS}`），避免以后新增 provider 时 KeyError；
`_ark_key()` 保留但 docstring 标注废弃供回滚。

复验：`--self-check` 只剩 MiniMax-M3 一行；scraped_raw 前 4 条实跑 4/4 成功。

## 遗留风险

评分回到**单点**（仅 MiniMax-M3）。MiniMax Token Plan 凌晨触顶时，
那批条目 0 分后被 `process_reviews.py` 的 `LOW_SCORE_CUTOFF = 2` 物理删除 ——
不是标低分，是从当天推荐里消失。要补备源，接入前必须先实调验证订阅状态。
