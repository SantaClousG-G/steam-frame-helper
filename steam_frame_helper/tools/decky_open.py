#!/usr/bin/env python3
"""Open the Decky panel inside the Steam UI on Steam Frame.

Steam Frame has no Quick Access Menu in VR, so Decky's QAM tab is never shown.
This script connects to Steam's CEF debugger (enabled by Decky via
.cef-enable-remote-debugging), registers a route that renders Decky's QAM tab
content as a regular page and navigates the Steam UI to it.

Usage: decky_open.py [panel|store|settings]
"""

import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from i18n import T  # noqa: E402

CEF_URL = "http://127.0.0.1:8080/json"
TARGET_TITLE = "SharedJSContext"
ROUTE = "/sfh-decky"
WAIT_SECONDS = 60

PAGES = {
    "panel": ROUTE,
    "store": "/decky/store",
    "settings": "/decky/settings",
}

# Registers ROUTE once per Steam UI session, then navigates.
JS_TEMPLATE = """
(() => {
  const d = window.DeckyPluginLoader;
  const nav = window.DFL && window.DFL.Navigation;
  if (!d || !nav || !d.routerHook || !d.tabsHook) return "not-ready";
  if (!window.__sfhDeckyRoute) {
    const React = window.SP_REACT;
    // Fallback when the SFH Frame Menu plugin is not loaded. tabsHook.render() wraps the
    // tab in Decky's QuickAccessVisibleState provider: without it plugin pages stay empty.
    const Panel = () => {
      const tab = React.useMemo(() => {
        const tabs = [];
        d.tabsHook.render(tabs, true);
        return tabs.find(t => t.key === 999) || null;
      }, []);
      if (!tab) return React.createElement("div", {style: {padding: "32px"}}, __NOT_LOADED__);
      return React.createElement("div",
        {style: {padding: "24px 32px", height: "100%", overflowY: "auto", boxSizing: "border-box"}},
        React.createElement("div",
          {style: {fontSize: "26px", fontWeight: "bold", marginBottom: "12px"}}, tab.title),
        tab.panel);
    };
    d.routerHook.addRoute(__ROUTE__, Panel, {exact: true});
    window.__sfhDeckyRoute = true;
  }
  nav.Navigate(__PATH__);
  return "ok";
})()
"""


class CDP:
    """Minimal Chrome DevTools Protocol client over a raw websocket."""

    def __init__(self, ws_url):
        host_port, path = ws_url[len("ws://"):].split("/", 1)
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0

    def _send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            header = struct.pack(">BB", 0x81, 0x80 | n)
        elif n < 65536:
            header = struct.pack(">BBH", 0x81, 0x80 | 126, n)
        else:
            header = struct.pack(">BBQ", 0x81, 0x80 | 127, n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(header + mask + masked)

    def _read(self, n):
        while len(self.rest) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("CEF closed the connection")
            self.rest += chunk
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def _recv(self):
        payload = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload += self._read(n)
            if b1 & 0x80:
                return json.loads(payload)

    def evaluate(self, expression):
        self.next_id += 1
        msg_id = self.next_id
        self._send({"id": msg_id, "method": "Runtime.evaluate",
                    "params": {"expression": expression, "returnByValue": True}})
        while True:
            msg = self._recv()
            if msg.get("id") == msg_id:
                return msg.get("result", {}).get("result", {}).get("value")


def find_target():
    targets = json.load(urllib.request.urlopen(CEF_URL, timeout=5))
    for t in targets:
        if t.get("title") == TARGET_TITLE:
            return t["webSocketDebuggerUrl"]
    return None


def main():
    page = sys.argv[1] if len(sys.argv) > 1 else "panel"
    if page not in PAGES:
        print(T("Неизвестная страница: {page}. Допустимо: {pages}",
                "Unknown page: {page}. Use one of: {pages}").format(page=page, pages=", ".join(PAGES)),
              file=sys.stderr)
        return 2
    js = (JS_TEMPLATE.replace("__ROUTE__", json.dumps(ROUTE))
          .replace("__PATH__", json.dumps(PAGES[page]))
          .replace("__NOT_LOADED__", json.dumps(T("Decky не загружен", "Decky is not loaded"))))

    deadline = time.time() + WAIT_SECONDS
    last_error = T("Steam UI не найден", "Steam UI not found")
    while time.time() < deadline:
        try:
            ws_url = find_target()
            if ws_url:
                result = CDP(ws_url).evaluate(js)
                if result == "ok":
                    print(T("Открыто: {page}", "Opened: {page}").format(page=PAGES[page]))
                    return 0
                last_error = T("Decky ещё не загрузился в Steam", "Decky has not loaded in Steam yet")
        except (OSError, ValueError, ConnectionError) as e:
            last_error = str(e)
        time.sleep(2)
    print(T("Не удалось открыть Decky: {err}", "Could not open Decky: {err}").format(err=last_error),
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
