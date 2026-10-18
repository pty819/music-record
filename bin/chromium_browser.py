#!/usr/bin/env python3
"""
chromium_browser.py — 取代 Camoufox REST 服务的 Chromium CDP 后端。

背景：原管道 5 个 Camoufox 站 + 3 个 HTML 抓取脚本（musique_machine /
all_about_jazz / mixmag_asia）通过 `http://127.0.0.1:9377` 的 REST 接口驱动
一个长期驻留的 Camoufox（Firefox 内核）实例。Camoufox 需要额外下载约 400MB
浏览器二进制 + 独立 systemd user unit，是整条管道唯一不能随 Hermes 一起搬走的
依赖。

本模块用 Hermes 自带的 Chromium（`/root/.hermes/tools/chromium-*/chrome-linux64/chrome`）
通过 CDP（Chrome DevTools Protocol）实现**完全相同的 REST 契约**，因此上层的
抓取脚本一行都不用改。

REST 契约（与原 Camoufox 服务一致）
-----------------------------------
  POST   /tabs                       {userId, sessionKey, url} → {tabId}
  POST   /tabs/{id}/navigate         {url}                    → {success, tabId}
  POST   /tabs/{id}/evaluate         {expression}             → {result}
  POST   /tabs/{id}/content          {}                       → {html}   (本实现新增)
  GET    /tabs/{id}/content                                     → {html}
  DELETE /tabs/{id}                                            → {closed}

`/tabs/{id}/evaluate` 的 `result` 字段直接返回 JS 表达式的 JSON 化结果 ——
与原实现一致，所以 `Array.from(...)` 之类返回数组的脚本无需任何改动。

用法
----
  1. 直接当库用（推荐，无端口占用、无并发问题）：
         from chromium_browser import fetch, evaluate
         html = fetch(url)
         rows = evaluate(url, "Array.from(document.querySelectorAll('a'))")
  2. 起 REST 服务，让旧脚本零改动连上来：
         python3 chromium_browser.py --serve --port 9377
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

DEFAULT_TIMEOUT = 90
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

# 反自动化/反爬常见检测点：抹掉最容易被 JS 指纹识别的两个特征。
# webdriver 已被 --disable-bell-busy 之类覆盖，这里只补 navigator.plugins 长度。
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
"""


# ── Chromium 定位 ────────────────────────────────────────────


def find_chromium() -> str:
    """定位可用的 Chromium/Chrome 可执行文件。

    优先用 Hermes 自带版本（随工具链分发，无需 apt），回退到系统 PATH。
    """
    env_override = os.environ.get("MUSIC_CHROMIUM_BIN")
    if env_override and os.path.exists(env_override):
        return env_override

    hermes_tools = Path_home_tools()
    if hermes_tools:
        for pattern in ("chromium-*/chrome-linux64/chrome", "chromium-*/chrome-linux/chrome"):
            hits = sorted(hermes_tools.glob(pattern))
            if hits:
                return str(hits[-1])

    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found

    raise RuntimeError(
        "找不到 Chromium。设置 MUSIC_CHROMIUM_BIN 指向 chrome 可执行文件，"
        "或安装系统 chromium。"
    )


def Path_home_tools():
    from pathlib import Path

    return Path.home() / ".hermes" / "tools"


# ── CDP 会话 ────────────────────────────────────────────────


class ChromiumSession:
    """一个 Chromium 实例 + 一条 CDP 连接。"""

    def __init__(self, *, headless: bool = True, timeout: int = DEFAULT_TIMEOUT,
                 user_agent: str = DEFAULT_UA):
        from websocket import create_connection  # 延迟导入

        self._create_connection = create_connection
        self.timeout = timeout
        self.user_agent = user_agent
        self._next_id = 0
        self.proc = None
        self.ws = None
        self._tmpdir = None
        self._started_headless = headless

    # ── 生命周期 ──

    def start(self) -> "ChromiumSession":
        binary = find_chromium()
        self._tmpdir = tempfile.mkdtemp(prefix="chromium-cdp-")
        port = _free_port()

        cmd = [
            binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self._tmpdir}",
            "--no-first-run",
            "--no-default-browser-check",
            # CDP 的 WebSocket 握手默认拒绝非空 Origin 的连接（Chrome ≥111）。
            # websocket-client 会带 Origin 头，所以必须显式放行，否则 403。
            "--remote-allow-origins=*",
            "--no-sandbox",              # 容器内以 root 运行，无 user ns
            "--disable-dev-shm-usage",   # /dev/shm 通常只有 64MB
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            f"--user-agent={self.user_agent}",
            "--hide-scrollbars",
            "--mute-audio",
            "--window-size=1920,1080",
            "about:blank",
        ]
        if self._started_headless:
            cmd.insert(1, "--headless=new")

        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        ws_url = self._wait_for_devtools(port)
        self.ws = self._create_connection(ws_url, timeout=self.timeout)
        # CDP 的 Page/Runtime 域是 per-target 的，browser 级连接上没有这些方法
        # （Page.enable → -32601）。所以先建一个 target 并 attach，后续带 sessionId 调用。
        target = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.default_session = self.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}
        )["sessionId"]
        # enable 后 Page.navigate 与 Runtime.evaluate 才生效
        self._session_call(self.default_session, "Page.enable")
        self._session_call(self.default_session, "Runtime.enable")
        self._session_call(
            self.default_session, "Page.addScriptToEvaluateOnNewDocument",
            {"source": _STEALTH_JS},
        )
        return self

    def _wait_for_devtools(self, port: int, timeout: float = 30.0) -> str:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Chromium 进程提前退出 (rc={self.proc.returncode})")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=2
                ) as r:
                    return json.loads(r.read().decode())["webSocketDebuggerUrl"]
            except Exception as e:  # noqa: BLE001 — 启动竞态，重试即可
                last = e
                time.sleep(0.25)
        raise RuntimeError(f"等待 Chromium DevTools 端点超时: {last}")

    def close(self) -> None:
        for closer in (
            lambda: self.ws.close(),
            lambda: self.proc.terminate(),
        ):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
        if self.proc:
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def __enter__(self) -> "ChromiumSession":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()

    # ── CDP 原语 ──

    def call(self, method: str, params: dict | None = None, timeout: float | None = None):
        self._next_id += 1
        msg_id = self._next_id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))

        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            self.ws.settimeout(max(0.5, deadline - time.time()))
            raw = self.ws.recv()
            if not raw:
                continue
            msg = json.loads(raw)
            if msg.get("id") != msg_id:
                continue  # 事件消息，忽略
            if "error" in msg:
                raise RuntimeError(f"CDP {method} 失败: {msg['error']}")
            return msg.get("result", {})
        raise TimeoutError(f"CDP {method} 超时 ({timeout or self.timeout}s)")

    # ── 高层操作 ──

    def open_tab(self, url: str, *, settle: float = 3.0) -> str:
        target = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        session_id = self.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}
        )["sessionId"]
        self._session_call(session_id, "Page.enable")
        self._session_call(session_id, "Runtime.enable")
        self._session_call(session_id, "Page.navigate", {"url": url})
        self._wait_ready(session_id, timeout=30)
        time.sleep(settle)  # 给 JS 渲染 / lazy-load 留时间
        return session_id

    def _wait_ready(self, session_id: str, timeout: float = 30.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._next_id += 1
            msg_id = self._next_id
            self.ws.send(json.dumps({
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {"expression": "document.readyState"},
                "sessionId": session_id,
            }))
            self.ws.settimeout(max(0.5, deadline - time.time()))
            msg = json.loads(self.ws.recv())
            if msg.get("id") == msg_id:
                if msg.get("result", {}).get("result", {}).get("value") in (
                    "interactive", "complete"
                ):
                    return
            time.sleep(0.2)

    def _session_call(self, session_id: str, method: str,
                      params: dict | None = None, timeout: float | None = None):
        self._next_id += 1
        msg_id = self._next_id
        self.ws.send(json.dumps({
            "id": msg_id, "method": method,
            "params": params or {}, "sessionId": session_id,
        }))
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            self.ws.settimeout(max(0.5, deadline - time.time()))
            msg = json.loads(self.ws.recv())
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                raise RuntimeError(f"CDP {method} 失败: {msg['error']}")
            return msg.get("result", {})
        raise TimeoutError(f"CDP {method} 超时")

    def evaluate(self, session_id: str, expression: str):
        """在页面上下文求值，返回 JSON 化的 JS 结果（数组/对象/标量）。

        兼容旧抓取脚本的两种写法：Camoufox 的 `/evaluate` 对函数表达式
        （`() => {...}`、`function(){...}`、裸 `return ...`）会自动调用一次，
        这里同样处理，否则只会拿到函数对象本身而不是它的返回值。
        """
        res = self._session_call(session_id, "Runtime.evaluate", {
            "expression": _invoke_if_function(expression),
            "returnByValue": True,
            "awaitPromise": True,
        })
        if res.get("exceptionDetails"):
            exc = res["exceptionDetails"]
            raise RuntimeError(
                f"JS 异常: {exc.get('text')} "
                f"{exc.get('exception', {}).get('description', '')}"
            )
        return res.get("result", {}).get("value")

    def html(self, session_id: str) -> str:
        return self._session_call(session_id, "Page.getFrameTree").get(
            "frameTree", {}
        ) and self._session_call(
            session_id, "Runtime.evaluate",
            {"expression": "document.documentElement.outerHTML", "returnByValue": True},
        )["result"].get("value", "")

    def close_tab(self, session_id: str) -> None:
        try:
            target_id = session_id.split(".")[-1]
            self.call("Target.closeTarget", {"targetId": target_id})
        except Exception:  # noqa: BLE001 — 关闭失败不影响出货
            pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_FN_RE = re.compile(r"^\s*(?:\(\s*\)|async\s*(?:\(\s*\)|function\s*\([^)]*\))\s*=>"
                    r"|function\s*(?:[A-Za-z_$][\w$]*)?\s*\([^)]*\)\s*\{)")


def _invoke_if_function(expression: str) -> str:
    """把「函数表达式」包装成立即调用，与 Camoufox `/evaluate` 的行为一致。

    旧抓取脚本普遍写成 `() => { ... }` 或 `function(){ return ... }`，
    直接求值只会得到函数对象本身。裸 `return ...` 的写法则包进 IIFE。
    """
    expr = expression.strip()
    if _FN_RE.match(expr):
        return f"({expr})()"
    if re.match(r"^\s*(async\s+)?return[\s{(]", expr):
        return f"(async function(){{ {expr} }})()"
    return expression


# ── 便捷函数（库用法） ──────────────────────────────────────


def fetch(url: str, *, settle: float = 3.0, timeout: int = DEFAULT_TIMEOUT) -> str:
    """打开 URL 并返回渲染后的 HTML。"""
    with ChromiumSession(timeout=timeout) as s:
        sid = s.open_tab(url, settle=settle)
        return s.html(sid)


def evaluate(url: str, expression: str, *, settle: float = 3.0,
             timeout: int = DEFAULT_TIMEOUT):
    """打开 URL，在页面上下文求值并返回 JSON 化结果。"""
    with ChromiumSession(timeout=timeout) as s:
        sid = s.open_tab(url, settle=settle)
        return s.evaluate(sid, expression)


# ── 进程内客户端（推荐给 bin/scrape_*.py 用） ──────────────


class LocalApiClient:
    """与 Camoufox REST 契约同形的进程内客户端，无需起 HTTP 服务。

    旧抓取脚本的 `_api(method, path, body)` 只要把实现换成
    `return _client.call(method, path, body)`，其余逻辑一行不用改。

    用法::

        from chromium_browser import LocalApiClient
        _client = LocalApiClient()
        tab = _client.call("POST", "/tabs", {"url": "https://example.com"})
        rows = _client.call("POST", f"/tabs/{tab['tabId']}/evaluate",
                            {"expression": "Array.from(document.links).length"})
        _client.call("DELETE", f"/tabs/{tab['tabId']}")
    """

    def __init__(self, *, settle: float = 3.0, timeout: int = DEFAULT_TIMEOUT):
        self.settle = settle
        self.timeout = timeout
        self._sessions: dict[str, tuple] = {}

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        body = body or {}
        parts = [p for p in path.split("/") if p]

        # POST /tabs
        if method == "POST" and parts == ["tabs"]:
            sess = ChromiumSession(timeout=self.timeout).start()
            sid = sess.open_tab(body.get("url", "about:blank"), settle=self.settle)
            tab_id = f"tab-{len(self._sessions)}-{id(sess) & 0xffff:04x}"
            self._sessions[tab_id] = (sess, sid)
            return {"tabId": tab_id}

        if len(parts) == 3 and parts[0] == "tabs":
            tab_id, action = parts[1], parts[2]
            entry = self._sessions.get(tab_id)
            if not entry:
                return {"error": f"unknown tabId {tab_id}"}
            sess, sid = entry

            if action == "navigate":
                sess.open_tab(body.get("url", "about:blank"), settle=self.settle)
                return {"success": True, "tabId": tab_id}
            if action == "evaluate":
                return {"result": sess.evaluate(sid, body.get("expression", "null"))}
            if action == "content":
                return {"html": sess.html(sid)}

        # DELETE /tabs/{id}
        if method == "DELETE" and len(parts) == 2 and parts[0] == "tabs":
            entry = self._sessions.pop(parts[1], None)
            if entry:
                entry[0].close()
            return {"closed": True}

        return {"error": f"unsupported: {method} {path}"}

    def close(self) -> None:
        for sess, _ in list(self._sessions.values()):
            sess.close()
        self._sessions.clear()

    def __enter__(self) -> "LocalApiClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ── REST 服务（兼容旧脚本） ─────────────────────────────────


class _Handler:
    """极简 WSGI 风格处理器，直接用 http.server。"""

    def __init__(self, session_factory):
        self.session_factory = session_factory


def serve(port: int = 9377, host: str = "127.0.0.1") -> None:
    """起 REST 服务，让 scrape_*.py 零改动连上来。

    每个请求开一条独立 CDP 会话（比维护 tab 池简单得多，且抓取脚本本身
    是串行的；并发由 scrape_html_parallel.py 的进程级并行提供）。
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    _TAB_RE = re.compile(r"^/tabs/([^/]+)/(navigate|evaluate|content)$")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # 静默：避免污染管道 stdout
            pass

        def _send(self, payload: dict, code: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:  # noqa: BLE001
                return {}

        # POST /tabs  → 新开 tab 并导航
        def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler 约定
            path = urlparse(self.path).path
            body = self._body()

            if path == "/tabs":
                tab_id = f"tab-{int(time.time() * 1000)}-{os.getpid()}"
                try:
                    sess = ChromiumSession().start()
                    sid = sess.open_tab(body.get("url", "about:blank"))
                    _SESSIONS[tab_id] = (sess, sid)
                    self._send({"tabId": tab_id})
                except Exception as e:  # noqa: BLE001
                    self._send({"error": str(e)}, 500)
                return

            m = _TAB_RE.match(path)
            if m:
                tab_id, action = m.group(1), m.group(2)
                entry = _SESSIONS.get(tab_id)
                if not entry:
                    self._send({"error": f"unknown tabId {tab_id}"}, 404)
                    return
                sess, sid = entry
                try:
                    if action == "navigate":
                        sess.open_tab(body.get("url", "about:blank"))
                        self._send({"success": True, "tabId": tab_id})
                    elif action == "evaluate":
                        self._send({"result": sess.evaluate(sid, body.get("expression", "null"))})
                    elif action == "content":
                        self._send({"html": sess.html(sid)})
                except Exception as e:  # noqa: BLE001
                    self._send({"error": str(e)}, 500)
                return

            self._send({"error": "not found"}, 404)

        # GET /tabs/{id}/content
        def do_GET(self):  # noqa: N802
            m = _TAB_RE.match(urlparse(self.path).path)
            if m and m.group(2) == "content":
                entry = _SESSIONS.get(m.group(1))
                if not entry:
                    self._send({"error": "unknown tabId"}, 404)
                    return
                sess, sid = entry
                try:
                    self._send({"html": sess.html(sid)})
                except Exception as e:  # noqa: BLE001
                    self._send({"error": str(e)}, 500)
                return
            self._send({"error": "not found"}, 404)

        # DELETE /tabs/{id}
        def do_DELETE(self):  # noqa: N802
            tab_id = urlparse(self.path).path.rstrip("/").split("/")[-1]
            entry = _SESSIONS.pop(tab_id, None)
            if entry:
                entry[0].close()
            self._send({"closed": True})

    _SESSIONS: dict = {}
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"chromium_browser REST 服务监听 http://{host}:{port} (Chromium CDP 后端)",
          file=sys.stderr, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for sess, _ in list(_SESSIONS.values()):
            sess.close()
        srv.server_close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serve", action="store_true", help="起 REST 服务")
    ap.add_argument("--port", type=int, default=9377)
    ap.add_argument("--self-check", action="store_true",
                    help="启动一次 Chromium，抓一个页面证明可用")
    args = ap.parse_args()

    if args.self_check:
        html = fetch("https://example.com", settle=1.0)
        ok = "<html" in html.lower()
        print(f"Chromium 自检: {'✅ 渲染成功' if ok else '❌ 未拿到 HTML'} "
              f"({len(html)} bytes)")
        print(f"  binary: {find_chromium()}")
        sys.exit(0 if ok else 1)

    if args.serve:
        serve(port=args.port)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
