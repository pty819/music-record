#!/usr/bin/env python3
"""
provider_failover.py — 多 LLM provider 容错层，供 process_reviews.py 使用。

设计目标：评分管道不再单点依赖 MiniMax。主 provider（MiniMax-M3）在
凌晨 Token Plan 配额耗尽 / 429 / 持续失败时，自动切换到备用 provider
（火山 Ark DeepSeek-v4-flash），保证每日推荐不中断。

provider 定义：
  1. MiniMax-M3 (Anthropic 兼容, api.minimaxi.com/anthropic)  ← 主
  2. Ark DeepSeek-v4-flash (OpenAI 兼容, ark.cn-beijing.volces.com/api/coding/v1) ← 备

使用：Python 侧直接 import，或用 --self-check 参数做连通性自检。
"""
import json
import os
import re
import sys
import time
from pathlib import Path

# ── provider 配置 ──────────────────────────────────────────

_ENV_PATH = Path.home() / ".hermes" / ".env"


def _read_env_key(var_name):
    """从 ~/.hermes/.env 读取单个 key（带引号/不带引号都支持）。"""
    if not _ENV_PATH.exists():
        return ""
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{var_name}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def _minimax_key():
    """MiniMax key 优先级：文件 > 环境变量 > .env。"""
    key_path = Path("/home/liyifan/.config/music-recs/minimax_cn_key")
    if key_path.exists():
        k = key_path.read_text(encoding="utf-8").strip()
        if k:
            return k
    return os.environ.get("MINIMAX_CN_API_KEY", "") or _read_env_key("MINIMAX_CN_API_KEY")


def _ark_key():
    """Ark key 优先级：环境变量 > .env。"""
    return (
        os.environ.get("HERMES_CUSTOM_ARK_CN_BEIJING_VOLCES_COM_API_KEY", "")
        or _read_env_key("HERMES_CUSTOM_ARK_CN_BEIJING_VOLCES_COM_API_KEY")
    )


PROVIDERS = [
    {
        "name": "minimax",
        "label": "MiniMax-M3",
        "api_mode": "anthropic",
        "base_url": "https://api.minimaxi.com/anthropic",
        "model": "MiniMax-M3",
        "key": _minimax_key(),
        "enabled": True,
    },
    {
        "name": "ark",
        "label": "Ark DeepSeek-v4-flash",
        "api_mode": "openai",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v1",
        "model": "deepseek-v4-flash-ga-260731",
        "key": _ark_key(),
        "enabled": True,
    },
]

MAX_TOKENS = 4096
TIMEOUT = 120
RETRIES = 2  # 每个 provider 内重试次数（熔断后换 provider 也算一次整体重试）

# 熔断状态（进程内共享）
_active_provider = 0
_breaker_open = False
_provider_stats = {"minimax": {"ok": 0, "fail": 0}, "ark": {"ok": 0, "fail": 0}}
_switch_log = []


# ── 底层调用 ───────────────────────────────────────────────


def _call_anthropic(provider, prompt_text):
    """Anthropic 兼容端点（MiniMax）。"""
    import anthropic

    client = anthropic.Anthropic(
        api_key=provider["key"],
        base_url=provider["base_url"],
        timeout=TIMEOUT,
    )
    message = client.messages.create(
        model=provider["model"],
        max_tokens=MAX_TOKENS,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt_text}],
    )
    text = ""
    for block in message.content:
        if hasattr(block, "type") and block.type == "text" and hasattr(block, "text"):
            text = block.text
            break
    return text


def _call_openai(provider, prompt_text):
    """OpenAI 兼容端点（火山 Ark）。"""
    import urllib.request

    payload = json.dumps({
        "model": provider["model"],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt_text}],
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{provider['base_url']}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {provider['key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    # 提取 content（DeepSeek 可能返回 reasoning_content，取 content 即可）
    content = body["choices"][0]["message"]["content"]
    return content


def _call(provider, prompt_text):
    if provider["api_mode"] == "anthropic":
        return _call_anthropic(provider, prompt_text)
    return _call_openai(provider, prompt_text)


# ── JSON 提取（复用 process_reviews 的三策略） ─────────────


def _extract_json(text):
    """从 LLM 响应提取 JSON 对象：直接解析 → markdown 代码块 → 正则找 total_score。"""
    if not text:
        return None
    # Strategy 1: direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strategy 2: markdown code block
    m = re.search(r"```(?:json)?\s*\n?({.*?})\n?\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Strategy 3: {...} with total_score
    m = re.search(r"(\{[^{}]*\"total_score\"\s*:\s*\d+[^{}]*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _is_quota_error(err_str):
    """判断是否是配额耗尽类错误（应切换 provider 而非重试）。"""
    quota_signals = (
        "2056", "用量上限", "quota", "Token Plan", "rate limit",
        "429", "too many requests", "insufficient",
    )
    return any(s in str(err_str).lower() for s in quota_signals)


# ── 对外 API ───────────────────────────────────────────────


def active_provider_index():
    return _active_provider


def active_provider():
    return PROVIDERS[_active_provider]


def get_stats():
    return dict(_provider_stats)


def get_switch_log():
    return list(_switch_log)


def switch_provider(reason, to_idx=None):
    """切换到指定 provider（默认下一个）。记录日志。"""
    global _active_provider, _breaker_open
    if to_idx is None:
        to_idx = (_active_provider + 1) % len(PROVIDERS)
    _active_provider = to_idx
    _breaker_open = False
    ts = time.strftime("%H:%M:%S")
    _switch_log.append(f"[{ts}] 切换到 {PROVIDERS[to_idx]['label']}: {reason}")
    print(f"    ⚡ 切换 provider → {PROVIDERS[to_idx]['label']} ({reason})", file=sys.stderr)


def is_available(idx=None):
    """探测 provider 是否健康（最小调用）。"""
    p = PROVIDERS[idx if idx is not None else _active_provider]
    if not p["key"]:
        return False
    try:
        text = _call(p, "回复 OK 两个字母即可")
        return "OK" in (text or "").upper()
    except Exception:
        return False


def call_with_failover(prompt_text):
    """带容错的单条评分调用。

    流程：
      1. 从当前 active provider 开始，逐个尝试（最多 len(PROVIDERS) 个）
      2. 配额/429 错误 → 立即切下一个 provider
      3. 网络/解析失败 → 重试 RETRIES 次后切下一个
      4. 所有 provider 都失败 → 返回 None
    返回: (score:int|None, genre:str|None, summary:str|None, provider:str)
    """
    global _active_provider
    start_idx = _active_provider
    tried = 0
    idx = start_idx

    while tried < len(PROVIDERS):
        p = PROVIDERS[idx]
        if not p["enabled"] or not p["key"]:
            tried += 1
            idx = (idx + 1) % len(PROVIDERS)
            continue

        attempts = 0
        last_err = ""
        exhausted = False
        while attempts <= RETRIES:
            try:
                text = _call(p, prompt_text)
                result = _extract_json(text)
                if result is None:
                    raise ValueError("cannot parse JSON from response")
                score = int(result.get("total_score", 0))
                genre = (result.get("genre") or "unknown").strip()
                summary = (result.get("cn_summary") or "").strip()
                score = max(1, min(10, score))
                _provider_stats[p["name"]]["ok"] += 1
                return score, genre, summary, p["name"]
            except Exception as e:
                last_err = str(e)
                _provider_stats[p["name"]]["fail"] += 1
                if _is_quota_error(last_err):
                    # 配额耗尽 → 立即切换，不重试
                    switch_provider(f"配额/限流: {last_err[:80]}", to_idx=(idx + 1) % len(PROVIDERS))
                    exhausted = True
                    break
                attempts += 1
                if attempts <= RETRIES:
                    delay = 2 ** (attempts - 1)
                    print(f"    [retry {attempts}/{RETRIES} {p['label']}] {last_err[:100]}", file=sys.stderr)
                    time.sleep(delay)
        # 重试用尽或配额错误 → 切下一个 provider
        if not exhausted:
            switch_provider(f"{p['label']} 重试{RETRIES}次仍失败: {last_err[:80]}",
                            to_idx=(idx + 1) % len(PROVIDERS))
        tried += 1
        idx = (idx + 1) % len(PROVIDERS)

    return None, None, None, "all-failed"


def self_check():
    """连通性自检：对每个 provider 做最小调用，报告可用性。"""
    print("=== provider_failover 自检 ===")
    for i, p in enumerate(PROVIDERS):
        status = "✅ 可用" if p["key"] else "❌ 无 key"
        print(f"  [{i}] {p['label']}  model={p['model']}  key={'有' if p['key'] else '无'}  {status}")
        if p["key"]:
            try:
                text = _call(p, "回复 OK 两个字母即可")
                ok = "OK" in (text or "").upper()
                print(f"      探测: {'✅ 返回 OK' if ok else '⚠️ 返回非 OK: ' + (text or '')[:80]}")
            except Exception as e:
                print(f"      探测: ❌ {str(e)[:120]}")
    print()


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        # 默认行为：像 OpenAI CLI 一样自检后退出（供手测）
        self_check()
