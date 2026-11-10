#!/usr/bin/env python3
"""Live view of the Steam UI on Steam Frame in a browser on the PC.

Games are composited by gamescope straight into the headset and cannot be
captured, but the Steam UI windows are CEF pages: this server takes
screenshots of them through the CEF debugger and forwards clicks back.
The page polls /frame (a plain JPEG) a few times per second.

Usage: ui_stream.py [port]   — open http://<frame-ip>:<port>/?t=<token>
The token is stored in ../ui_stream.token (created on first start).
"""

import base64
import json
import os
import secrets
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decky_open import CDP, CEF_URL  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8091
TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "ui_stream.token")
MAIN_TARGET = "SteamVR"
JPEG_QUALITY = 65

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Steam Frame UI</title>
<style>
 body { margin: 0; background: #111; color: #ddd; font: 14px system-ui, sans-serif; }
 header { display: flex; gap: 12px; align-items: center; padding: 8px 12px; background: #1b1e24; flex-wrap: wrap; }
 select, button { background: #2a2f38; color: #ddd; border: 1px solid #444; border-radius: 6px; padding: 4px 8px; }
 #hint { color: #888; margin-left: auto; }
 #fps { color: #888; min-width: 60px; }
 img { display: block; max-width: 100vw; max-height: calc(100vh - 48px); margin: 0 auto; cursor: crosshair; }
</style></head><body>
<header>
 <b>Steam Frame UI</b>
 <select id="target"></select>
 <button id="back">Назад</button>
 <span id="fps"></span>
 <span id="hint">Клик по картинке = клик в Steam · колесо = прокрутка</span>
</header>
<img id="view" alt="">
<script>
const token = new URLSearchParams(location.search).get("t") || "";
const sel = document.getElementById("target"), img = document.getElementById("view");
const fps = document.getElementById("fps");
const q = (extra) => "t=" + encodeURIComponent(token) + "&target=" + encodeURIComponent(sel.value) + (extra || "");
let frames = 0;
setInterval(() => { fps.textContent = frames + " к/с"; frames = 0; }, 1000);
async function loop() {
  for (;;) {
    try {
      const r = await fetch("/frame?" + q("&r=" + Date.now()), {cache: "no-store"});
      if (!r.ok) throw new Error(r.status);
      const url = URL.createObjectURL(await r.blob());
      const old = img.src;
      img.src = url;
      if (old.startsWith("blob:")) URL.revokeObjectURL(old);
      frames++;
      await new Promise(res => setTimeout(res, 150));
    } catch (e) {
      fps.textContent = "нет связи";
      await new Promise(res => setTimeout(res, 1500));
    }
  }
}
function point(e) {
  const r = img.getBoundingClientRect();
  return "&x=" + Math.round((e.clientX - r.left) * img.naturalWidth / r.width)
       + "&y=" + Math.round((e.clientY - r.top) * img.naturalHeight / r.height);
}
img.addEventListener("click", e => fetch("/click?" + q(point(e)), {method: "POST"}));
img.addEventListener("wheel", e => { e.preventDefault();
  fetch("/scroll?" + q(point(e) + "&dy=" + Math.round(e.deltaY)), {method: "POST"}); }, {passive: false});
document.getElementById("back").onclick = () => fetch("/back?" + q(), {method: "POST"});
fetch("/targets?t=" + encodeURIComponent(token)).then(r => r.json()).then(list => {
  for (const name of list) { const o = document.createElement("option"); o.value = o.textContent = name; sel.appendChild(o); }
  loop();
});
</script></body></html>
"""


def load_token():
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            token = f.read().strip()
            if token:
                return token
    except OSError:
        pass
    token = secrets.token_urlsafe(12)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)
    os.chmod(TOKEN_FILE, 0o600)
    return token


TOKEN = load_token()


def cef_pages():
    return json.load(urllib.request.urlopen(CEF_URL, timeout=5))


def targets():
    """Steam UI windows, main window first."""
    names = [p["title"] for p in cef_pages()
             if p.get("type") == "page" and p["title"].startswith(MAIN_TARGET)]
    names.sort(key=lambda n: (n != MAIN_TARGET, n))
    return names


class Sessions:
    """One persistent CDP connection per Steam UI window, reconnect on failure."""

    def __init__(self):
        self.lock = threading.Lock()
        self.conns = {}

    def _connect(self, title):
        if not title.startswith(MAIN_TARGET):
            raise LookupError(f"Недопустимое окно: {title}")
        for p in cef_pages():
            if p["title"] == title:
                return CDP(p["webSocketDebuggerUrl"])
        raise LookupError(f"Окно не найдено: {title}")

    @staticmethod
    def _call(cdp, method, params):
        cdp.next_id += 1
        msg_id = cdp.next_id
        cdp._send({"id": msg_id, "method": method, "params": params})
        while True:
            msg = cdp._recv()
            if msg.get("id") == msg_id:
                return msg.get("result", {})

    def call(self, title, method, params=None):
        with self.lock:
            for attempt in (1, 2):
                cdp = self.conns.get(title)
                try:
                    if cdp is None:
                        cdp = self.conns[title] = self._connect(title)
                    return self._call(cdp, method, params or {})
                except (OSError, ConnectionError, ValueError):
                    self.conns.pop(title, None)
                    if attempt == 2:
                        raise


SESSIONS = Sessions()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _params(self):
        url = urllib.parse.urlparse(self.path)
        return url.path, {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}

    def _authorized(self, params):
        if secrets.compare_digest(params.get("t", ""), TOKEN):
            return True
        self.send_error(403, "Bad token")
        return False

    def _reply(self, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path, params = self._params()
        if not self._authorized(params):
            return
        try:
            if path == "/":
                self._reply(PAGE, "text/html; charset=utf-8")
            elif path == "/targets":
                self._reply(json.dumps(targets(), ensure_ascii=False))
            elif path == "/frame":
                res = SESSIONS.call(params.get("target", MAIN_TARGET), "Page.captureScreenshot",
                                    {"format": "jpeg", "quality": JPEG_QUALITY})
                self._reply(base64.b64decode(res.get("data", "")), "image/jpeg")
            else:
                self.send_error(404)
        except (LookupError, OSError, ConnectionError, ValueError) as e:
            self.send_error(503, str(e))

    def do_POST(self):
        path, params = self._params()
        if not self._authorized(params):
            return
        target = params.get("target", MAIN_TARGET)
        try:
            if path == "/click":
                x, y = float(params["x"]), float(params["y"])
                for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
                    SESSIONS.call(target, "Input.dispatchMouseEvent",
                                  {"type": kind, "x": x, "y": y, "button": "left",
                                   "clickCount": 1})
            elif path == "/scroll":
                SESSIONS.call(target, "Input.dispatchMouseEvent",
                              {"type": "mouseWheel", "x": float(params["x"]),
                               "y": float(params["y"]), "deltaX": 0,
                               "deltaY": float(params.get("dy", 0))})
            elif path == "/back":
                for kind in ("keyDown", "keyUp"):
                    SESSIONS.call(target, "Input.dispatchKeyEvent",
                                  {"type": kind, "key": "Escape", "code": "Escape",
                                   "windowsVirtualKeyCode": 27})
            else:
                self.send_error(404)
                return
            self._reply("{}")
        except (LookupError, OSError, ConnectionError, KeyError, ValueError) as e:
            self.send_error(503, str(e))


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print(f"http://0.0.0.0:{PORT}/?t={TOKEN}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
