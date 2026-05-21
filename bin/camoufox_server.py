#!/usr/bin/env python3
"""Camoufox REST API server for Hermes Agent (ARM64 compatible)."""
import json, os, signal, sys, threading, time, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from camoufox import Camoufox

HOST = os.environ.get("CAMOFOX_HOST", "127.0.0.1")
PORT = int(os.environ.get("CAMOFOX_PORT", "9377"))

IDLE_TIMEOUT = int(os.environ.get("CAMOFOX_IDLE_TIMEOUT", "300"))  # 5 min default
REAPER_INTERVAL = int(os.environ.get("CAMOFOX_REAPER_INTERVAL", "60"))  # check every 60s

_camoufox = None          # Camoufox instance
_default_ctx = None       # shared browser context
_tabs = {}                # tab_id -> {"page": ..., "user_id": ..., "session_key": ..., "last_activity": float}
_tabs_lock = threading.Lock()
_reaper_running = False


def _ensure_browser():
    global _camoufox, _default_ctx
    if _camoufox is None:
        b = Camoufox(headless=True, humanize=True)
        b.start()
        _camoufox = b
    if _default_ctx is None:
        _default_ctx = _camoufox.browser.new_context()
    return _camoufox, _default_ctx


def _touch_tab(tid):
    """Update the last-activity timestamp for a tab."""
    with _tabs_lock:
        t = _tabs.get(tid)
        if t:
            t["last_activity"] = time.time()


def _reaper_tabs():
    """Background thread: close tabs idle longer than IDLE_TIMEOUT."""
    global _reaper_running
    _reaper_running = True
    while _reaper_running:
        time.sleep(REAPER_INTERVAL)
        now = time.time()
        to_close = []
        with _tabs_lock:
            for tid, t in list(_tabs.items()):
                idle = now - t.get("last_activity", now)
                if idle >= IDLE_TIMEOUT:
                    to_close.append((tid, t.get("user_id", "?")))
        for tid, uid in to_close:
            tab = _tabs.pop(tid, None)
            if tab:
                try:
                    tab["page"].close()
                except Exception:
                    pass
                print(f"[camoufox] Reaped idle tab {tid} (user={uid}, idle>{IDLE_TIMEOUT}s)", file=sys.stderr)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[camoufox] {args[0]} {args[1]} {args[2]}", file=sys.stderr)

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _err(self, msg, status=400):
        self._json({"error": msg}, status)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        p = urlparse(self.path).path.rstrip("/")
        if p == "/health":
            self._json({"ok": True, "engine": "camoufox",
                        "browserConnected": _camoufox is not None,
                        "browserRunning": _camoufox is not None,
                        "activeTabs": len(_tabs),
                        "activeSessions": len(set(t.get("user_id") for t in _tabs.values())),
                        "consecutiveFailures": 0})
        elif p.startswith("/tabs/") and "snapshot" in p:
            self._do_snapshot(p.split("/")[2])
        elif p.startswith("/tabs/") and "screenshot" in p:
            self._do_screenshot(p.split("/")[2])
        elif p.startswith("/tabs/") and "images" in p:
            self._do_images(p.split("/")[2])
        elif p.startswith("/tabs/"):
            self._do_tab_info(p.split("/")[2])
        else:
            self._err("Not found", 404)

    def do_POST(self):
        p = urlparse(self.path).path.rstrip("/")
        b = self._body()
        if p == "/tabs":
            uid = b.get("userId", "")
            sk = b.get("sessionKey", "")
            url = b.get("url", "")
            if not uid or not sk:
                return self._err("userId and sessionKey required")
            try:
                _, ctx = _ensure_browser()
                page = ctx.new_page()
                tid = str(uuid.uuid4())
                with _tabs_lock:
                    _tabs[tid] = {"page": page, "user_id": uid, "session_key": sk, "last_activity": time.time()}
                if url:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                self._json({"tabId": tid, "url": page.url, "title": page.title()})
            except Exception as e:
                self._err(str(e), 500)
        elif "/navigate" in p:
            self._do_navigate(p.split("/")[2], b)
        elif "/click" in p:
            self._do_click(p.split("/")[2], b)
        elif "/type" in p:
            self._do_type(p.split("/")[2], b)
        elif "/scroll" in p:
            self._do_scroll(p.split("/")[2], b)
        elif "/press" in p:
            self._do_press(p.split("/")[2], b)
        elif "/back" in p:
            self._do_back(p.split("/")[2])
        elif "/evaluate" in p:
            self._do_evaluate(p.split("/")[2], b)
        else:
            self._err("Not found", 404)

    def do_DELETE(self):
        p = urlparse(self.path).path.rstrip("/")
        if p.startswith("/tabs/"):
            tid = p.split("/")[2]
            tab = _tabs.pop(tid, None)
            if tab:
                try:
                    tab["page"].close()
                except Exception:
                    pass
                self._json({"ok": True, "closed": tid})
            else:
                self._err("Tab not found", 404)
        elif p.startswith("/sessions/"):
            user_id = p.split("/")[2]
            closed = []
            with _tabs_lock:
                for tid, t in list(_tabs.items()):
                    if t.get("user_id") == user_id:
                        try:
                            t["page"].close()
                        except Exception:
                            pass
                        closed.append(tid)
                        del _tabs[tid]
            self._json({"ok": True, "closed_count": len(closed), "closed_tabs": closed})
        else:
            self._err("Not found", 404)

    # ---- internal helpers ----

    def _tab(self, tid):
        with _tabs_lock:
            t = _tabs.get(tid)
        if not t:
            self._err("Tab not found", 404)
        return t

    def _do_tab_info(self, tid):
        t = self._tab(tid)
        if t:
            _touch_tab(tid)
            self._json({"url": t["page"].url, "title": t["page"].title()})

    def _do_snapshot(self, tid):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        try:
            import re
            content = t["page"].content()
            # Basic snapshot: extract interactive elements
            interactive = t["page"].query_selector_all(
                "button, a, input, select, textarea, [role=button], [tabindex]"
            )
            parts = []
            for i, el in enumerate(interactive):
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                text = (el.inner_text() or "")[:60]
                parts.append(f"[{tag} e{i+1}] {text}")
            # Add non-interactive content too
            body_text = t["page"].evaluate("() => document.body?.innerText?.slice(0, 6000) || ''")
            snapshot = "\n".join(parts)
            if body_text:
                snapshot += "\n\n--- page text ---\n" + body_text

            self._json({
                "snapshot": snapshot,
                "refsCount": len(parts),
                "url": t["page"].url,
                "title": t["page"].title(),
            })
        except Exception as e:
            self._err(str(e), 500)

    def _do_screenshot(self, tid):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        try:
            import base64
            data = t["page"].screenshot(full_page=True)
            self._json({"screenshot": base64.b64encode(data).decode(),
                        "url": t["page"].url, "title": t["page"].title()})
        except Exception as e:
            self._err(str(e), 500)

    def _do_images(self, tid):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        try:
            imgs = t["page"].query_selector_all("img")
            result = []
            for img in imgs:
                src = img.get_attribute("src") or ""
                alt = img.get_attribute("alt") or ""
                if src:
                    result.append({"src": src, "alt": alt})
            self._json({"images": result})
        except Exception as e:
            self._err(str(e), 500)

    def _do_navigate(self, tid, body):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        url = body.get("url", "")
        if not url:
            return self._err("url required")
        try:
            t["page"].goto(url, wait_until="domcontentloaded", timeout=30000)
            self._json({"ok": True, "url": t["page"].url, "title": t["page"].title()})
        except Exception as e:
            self._err(str(e), 500)

    def _do_click(self, tid, body):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        ref = body.get("ref", "")
        if not ref:
            return self._err("ref required")
        try:
            ref_clean = ref.lstrip("@")
            idx = int(ref_clean[1:]) if ref_clean.startswith("e") and ref_clean[1:].isdigit() else 0
            els = t["page"].query_selector_all(
                "button, a, input, select, textarea, [role=button], [tabindex]"
            )
            if 0 < idx <= len(els):
                els[idx - 1].click()
            else:
                t["page"].query_selector(ref_clean).click()
            self._json({"ok": True, "clicked": ref, "url": t["page"].url})
        except Exception as e:
            self._err(str(e), 500)

    def _do_type(self, tid, body):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        ref = body.get("ref", "")
        text = body.get("text", "")
        if not ref or not text:
            return self._err("ref and text required")
        try:
            ref_clean = ref.lstrip("@")
            idx = int(ref_clean[1:]) if ref_clean.startswith("e") and ref_clean[1:].isdigit() else 0
            els = t["page"].query_selector_all(
                "button, a, input, select, textarea, [role=button], [tabindex]"
            )
            if 0 < idx <= len(els):
                els[idx - 1].fill(text)
            else:
                t["page"].query_selector(ref_clean).fill(text)
            self._json({"ok": True, "typed": text, "element": ref})
        except Exception as e:
            self._err(str(e), 500)

    def _do_scroll(self, tid, body):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        d = body.get("direction", "down")
        try:
            if d == "down":
                t["page"].evaluate("window.scrollBy(0, window.innerHeight)")
            else:
                t["page"].evaluate("window.scrollBy(0, -window.innerHeight)")
            self._json({"ok": True, "scrolled": d})
        except Exception as e:
            self._err(str(e), 500)

    def _do_press(self, tid, body):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        key = body.get("key", "")
        if not key:
            return self._err("key required")
        try:
            t["page"].keyboard.press(key)
            self._json({"ok": True, "pressed": key})
        except Exception as e:
            self._err(str(e), 500)

    def _do_back(self, tid):
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        try:
            t["page"].go_back()
            self._json({"ok": True, "url": t["page"].url})
        except Exception as e:
            self._err(str(e), 500)

    def _do_evaluate(self, tid, body):
        """Evaluate JavaScript expression in the page context."""
        t = self._tab(tid)
        if not t:
            return
        _touch_tab(tid)
        expression = body.get("expression", "")
        if not expression:
            return self._err("expression required")
        try:
            result = t["page"].evaluate(expression)
            # Playwright returns JSON-serializable values. For DOM nodes or
            # unserializable results, default=str converts them safely.
            try:
                json.dumps(result)
            except (TypeError, ValueError):
                result = str(result)
            self._json({"result": result})
        except Exception as e:
            # Return JS errors as a structured result so Hermes can surface them
            self._json({"result": None, "error": str(e)})


def _cleanup():
    global _camoufox, _default_ctx, _reaper_running
    print("[camoufox] Shutting down...", file=sys.stderr)
    _reaper_running = False
    for tid, t in list(_tabs.items()):
        try:
            t["page"].close()
        except Exception:
            pass
    _tabs.clear()
    if _default_ctx:
        try:
            _default_ctx.close()
        except Exception:
            pass
    if _camoufox:
        try:
            _camoufox.browser.close()
        except Exception:
            pass
        _camoufox = None


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"[camoufox] Server running on http://{HOST}:{PORT}", file=sys.stderr)
    print(f"[camoufox] Idle timeout={IDLE_TIMEOUT}s, reaper interval={REAPER_INTERVAL}s", file=sys.stderr)

    reaper_thread = threading.Thread(target=_reaper_tabs, daemon=True)
    reaper_thread.start()

    def sig(signum, frame):
        _cleanup()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig)
    signal.signal(signal.SIGTERM, sig)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup()
        server.server_close()


if __name__ == "__main__":
    main()