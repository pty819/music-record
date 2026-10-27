#!/usr/bin/env python3
"""
camofox_client.py — Camofox（Camoufox 反检测 Firefox）REST 客户端。

背景
----
2026-10-18 的迁移把管道里所有打 `http://127.0.0.1:9377` 的脚本换成了
`chromium_browser.py` 的 Chromium CDP 后端，理由是 Camoufox 需要额外 400MB
浏览器二进制 + 独立 systemd unit，是「唯一不能随 Hermes 一起搬走的依赖」。

现在 Camofox 已经作为常驻服务装在这台机器上
（camofox.service → 127.0.0.1:9377，引擎在 /root/.cache/camoufox），
那条理由不成立了。而 Chromium CDP 相比 Camoufox 缺了一样关键能力：
**指纹伪装**。all_about_jazz / mixmag_asia / musique_machine / downbeat
都是 Cloudflare 站，裸 Chromium 更容易被识别。

本模块提供与 `chromium_browser.LocalApiClient` **完全同形**的 `call()`
接口，把请求转给 Camofox REST 服务。调用方只需换 import，逻辑一行不改。

契约对照
--------
  POST   /tabs                {userId, sessionKey, url} → {tabId, ...}
  POST   /tabs/{id}/navigate  {userId, url}            → {success, ...}
  POST   /tabs/{id}/evaluate  {userId, expression}     → {result}
  DELETE /tabs/{id}           userId 放 query 或 body   → {ok}

注意 userId 的位置差异（Camofox 的 GET 路由只认 query string）：
  GET    /tabs/{id}/snapshot  ?userId=...   ← query only
  GET    /tabs                ?userId=...
  POST   /tabs/{id}/evaluate  userId 在 body

用法
----
  from camofox_client import CamofoxClient
  _client = CamofoxClient(user_id="scraper_xxx", session_key="session_xxx")
  tab = _client.call("POST", "/tabs", {"url": "https://example.com"})
  rows = _client.call("POST", f"/tabs/{tab['tabId']}/evaluate",
                       {"expression": "Array.from(document.links).length"})
  _client.call("DELETE", f"/tabs/{tab['tabId']}")
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:9377"


class CamofoxError(RuntimeError):
    """Camofox REST 调用失败。"""


class CamofoxClient:
    """与 LocalApiClient 同形的 Camofox 客户端。

    与 LocalApiClient 的差别只在底层：LocalApiClient 在本进程内用 CDP 驱动
    一个临时 Chromium；本类把请求发给常驻的 Camofox 服务（HTTP）。

    每个实例绑定一对 (user_id, session_key)——Camofox 按 userId 隔离会话与
    cookie/profile，所以不同站点用不同 user_id，避免 cookie 串味。
    """

    def __init__(
        self,
        *,
        user_id: str,
        session_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        settle: float = 3.0,
        retries: int = 2,
    ):
        self.user_id = user_id
        self.session_key = session_key or f"session_{user_id}"
        self.base_url = (base_url or os.environ.get("CAMOFOX_URL") or DEFAULT_URL).rstrip("/")
        self.timeout = timeout
        # settle 在 CDP 实现里是「导航后等页面稳定」的秒数。Camofox 自己做
        # 导航等待，这里保留参数只为同形；需要更久可调大。
        self.settle = settle
        # 建 tab 要 fork 一个 Firefox 进程（~230MB）。这台机器只有 1.6G 内存，
        # 内存吃紧时 fork 会超时，服务端返回 500 "tab create timed out"。
        # 重试前先清掉自己名下的旧 tab，再等一拍让内存回收。
        self.retries = retries

    # ── 低层 HTTP ────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict | None) -> dict:
        url = f"{self.base_url}{path}"
        payload = dict(body or {})
        # POST /tabs 需要 userId + sessionKey；其余 POST 路由（evaluate /
        # navigate）只从 body 读 userId。Camofox 的 GET 路由反过来——只认
        # query string，所以 GET 在 call() 里另行拼到 path 上。
        if method == "POST":
            payload.setdefault("userId", self.user_id)
            if path.rstrip("/") == "/tabs":
                payload.setdefault("sessionKey", self.session_key)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise CamofoxError(f"HTTP {e.code} {method} {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise CamofoxError(
                f"Camofox 服务不可达 ({url}): {e.reason}. "
                f"先启动: systemctl start camofox"
            ) from e

        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    # ── LocalApiClient 同形的 call() ─────────────────────────────────

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        """LocalApiClient 同形接口：返回 dict，失败时带 error 字段。"""
        method = method.upper()
        parts = [p for p in path.split("/") if p]
        payload = dict(body or {})
        try:
            if method == "GET":
                # Camofox 的 GET 路由只从 query string 读 userId。
                if "userId" not in payload:
                    payload["userId"] = self.user_id
                sep = "&" if "?" in path else "?"
                path = f"{path}{sep}{_qs(payload)}"
                payload = {}

            resp = self._request(method, path, payload)
        except CamofoxError as e:
            return {"error": str(e)}

        if method == "POST" and parts == ["tabs"]:
            if "tabId" not in resp:
                return {"error": f"camofox did not return tabId: {str(resp)[:200]}"}
            return resp

        if method == "DELETE" and len(parts) == 2 and parts[0] == "tabs":
            # Camofox 的 DELETE 认 query 或 body，两边都给。
            resp.setdefault("closed", True)
            return resp

        if method == "POST" and len(parts) == 3 and parts[1] != "tabs":
            # ── evaluate 的函数体兼容层 ──
            # Chromium 的 CDP Runtime.evaluate 会把 `() => {...}` 当函数体执行；
            # Camofox 的 evaluate 只接受**表达式**，传裸函数体会静默返回
            # {"ok": true} 而没有 result 字段 —— 调用方拿到 None。
            # 抓取脚本的提取 JS 全是箭头函数体，所以在这里统一包成 IIFE。
            if parts[2] == "evaluate":
                expr = str((body or {}).get("expression", "") or "").strip()
                if expr.startswith("()") and not expr.startswith("(()"):
                    resp = self._evaluate_iife(parts[1], expr)
            return resp

        return resp

    def _evaluate_iife(self, tab_id: str, fn_expr: str) -> dict:
        """把箭头函数体包成 IIFE 再执行。

        `() => {...}` → `(() => {...})()`
        """
        body = fn_expr
        if body.startswith("()"):
            body = "(" + body + ")"
        wrapped = f"({body})()"
        try:
            return self._request(
                "POST", f"/tabs/{tab_id}/evaluate", {"expression": wrapped}
            )
        except CamofoxError as e:
            return {"error": str(e)}

    # ── 建 tab 的重试与恢复 ───────────────────────────────────────────

    def _close_own_tabs(self) -> None:
        """关掉自己名下的所有 tab，释放 Firefox 进程内存。"""
        try:
            listing = self._request("GET", "/tabs", {"userId": self.user_id})
        except CamofoxError:
            return
        for t in listing.get("tabs", []) or []:
            tid = t.get("tabId")
            if not tid:
                continue
            try:
                self._request("DELETE", f"/tabs/{tid}", {"userId": self.user_id})
            except CamofoxError:
                pass

    def open_tab(self, url: str, *, retries: int | None = None) -> dict:
        """POST /tabs with retry.

        建 tab 时服务端要 fork 一个 Firefox 进程（约 230MB）。这台机器只有
        1.6G 内存，内存紧张时 fork 会超过服务端的 30s 上限并返回 500
        "tab create timed out"。重试前先清掉自己名下的残留 tab，让内存
        回收 —— 这正是本机 2026-10-27 排障时观察到的失败模式。
        """
        attempts = (self.retries if retries is None else retries) + 1
        last: dict = {}
        for attempt in range(attempts):
            last = self.call("POST", "/tabs", {"url": url})
            if last.get("tabId"):
                return last
            if attempt < attempts - 1:
                self._close_own_tabs()
                time.sleep(3 + attempt * 3)
        return last

    def navigate_fast(self, tab_id: str, url: str) -> dict:
        """快速导航：evaluate 里改 location.href，不等 commit。

        Camofox 的 POST /tabs/:id/navigate 内部是
        `page.goto(url, {waitUntil: 'commit'})` + `waitForLoadState
        ('domcontentloaded')` —— 实测在 Cloudflare 站上要 **17-36 秒**一篇，
        因为它要等 CF 挑战走完才 commit。

        改成在页面里执行 `window.location.href = url`：evaluate 立刻返回
        （~0.4s），CF 挑战在后台继续，我们只需要轮询等正文出现。
        实测同一篇 1.7s 拿到 4023 字符完整正文，快 10-20 倍。

        注意：evaluate 请求本身可能在导航过程中被页面中断，所以调用方
        仍需用 wait_for_content 轮询等结果，不要指望这次 evaluate 有返回。
        """
        expr = f"window.location.href = {json.dumps(url)}; 'navigating'"
        try:
            return self._request(
                "POST", f"/tabs/{tab_id}/evaluate", {"expression": expr}
            )
        except CamofoxError as e:
            return {"error": str(e)}

    def close(self) -> None:
        """Camofox 的 tab 生命周期归服务端管，这里没有本地资源可释放。"""

    def __enter__(self) -> "CamofoxClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _qs(payload: dict) -> str:
    from urllib.parse import urlencode

    return urlencode({k: v for k, v in payload.items() if v is not None})


def wait_for_content(
    client: "CamofoxClient",
    tab_id: str,
    expression: str,
    *,
    attempts: int = 12,
    delay: float = 1.0,
    predicate=None,
):
    """轮询 evaluate 直到拿到非空结果。

    Camofox 走真实 Firefox 网络栈，页面渲染比 Chromium/CDP 慢。抓取脚本
    原来用固定 sleep（1.2s / 2s / 3s）等页面就绪，在 CF 站上会提前提取 →
    正文为空（实测 all_about_jazz 的 Metakosmos 那篇首次 0 字符，重试即
    10.3K）。改成轮询直到拿到内容才停。

    `predicate` 可选，用于判断结果是否"算成功"（默认非空即算）。
    返回最后一次 evaluate 的 result。
    """
    import time as _time

    last = None
    for _ in range(max(1, attempts)):
        resp = client.call("POST", f"/tabs/{tab_id}/evaluate", {"expression": expression})
        last = resp.get("result")
        if predicate is not None:
            if predicate(last):
                return last
        elif last:
            return last
        _time.sleep(delay)
    return last


# 与旧脚本同名的便捷函数（chromium_browser.py 也提供过）。
def fetch(url: str, *, user_id: str = "fetch", timeout: int = 120) -> str:
    """打开 url 并返回页面 HTML。"""
    client = CamofoxClient(user_id=user_id, timeout=timeout)
    try:
        tab = client.open_tab(url)
        tab_id = tab.get("tabId")
        if not tab_id:
            return ""
        html = client.call("POST", f"/tabs/{tab_id}/evaluate",
                           {"expression": "document.documentElement.outerHTML"})
        client.call("DELETE", f"/tabs/{tab_id}")
        return str(html.get("result") or "")
    finally:
        client.close()


def evaluate(url: str, expression: str, *, user_id: str = "evaluate", timeout: int = 120):
    """打开 url 并执行 JS 表达式，返回其 JSON 化结果。"""
    client = CamofoxClient(user_id=user_id, timeout=timeout)
    try:
        tab = client.open_tab(url)
        tab_id = tab.get("tabId")
        if not tab_id:
            return None
        out = client.call("POST", f"/tabs/{tab_id}/evaluate", {"expression": expression})
        client.call("DELETE", f"/tabs/{tab_id}")
        return out.get("result")
    finally:
        client.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Camofox 客户端自检")
    ap.add_argument("--url", default="https://example.com")
    ap.add_argument("--user-id", default="selftest")
    args = ap.parse_args()

    c = CamofoxClient(user_id=args.user_id)
    tab = c.call("POST", "/tabs", {"url": args.url})
    print("POST /tabs ->", str(tab)[:200])
    tid = tab.get("tabId")
    if tid:
        print("evaluate  ->", str(c.call("POST", f"/tabs/{tid}/evaluate",
                                          {"expression": "document.title"}))[:200])
        c.call("DELETE", f"/tabs/{tid}")
