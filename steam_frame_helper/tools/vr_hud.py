#!/usr/bin/env python3
"""VR HUD for Steam Frame: a small head-locked SteamVR overlay with live streaming stats.

Data sources (refreshed several times per second):
  * Steam's own VR streaming link stats, the same numbers as in the Quick Access
    "streaming" panel: per link (wireless adapter, Wi-Fi) the ping and packet loss
    measured by the streaming client itself. Read from the Steam UI JS context
    (window.streamingStore) over the CEF DevTools port 127.0.0.1:8080. Steam updates
    them about once per second; "ping" there is p100 = the worst round trip of the
    last measurement window, which is what you feel as a stutter.
  * Kernel interface counters (/proc/net/dev): real traffic on each link, 1 s window.
  * iw: signal and PHY rates of the adapter SoftAP (wlanap) and home Wi-Fi (wlan0).
  * battery.

The overlay uses the OpenVR C function table (FnTable:IVROverlay_028, layout from the
public OpenVR SDK openvr_capi.h) via ctypes; frames go through a GL texture (EGL,
no window) with SetOverlayTexture. Show/hide: SIGUSR1 (SFH button). Text is drawn
in Python from a glyph atlas rendered once by ffmpeg at start-up (no per-frame
processes), so the HUD can refresh at 4+ Hz cheaply.
Settings: ~/.config/steam_frame_helper/vr_hud.json (position in metres relative to the
headset, width, opacity, refresh interval). Runs as the user; retries until SteamVR is up.
"""

import base64
import collections
import ctypes
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from i18n import T  # noqa: E402

LIB = "/opt/steamvr/bin/linuxarm64/libopenvr_api.so"
FONT = "/usr/share/fonts/TTF/Hack-Regular.ttf"
CONFIG = os.path.expanduser("~/.config/steam_frame_helper/vr_hud.json")
WORK = os.path.join(tempfile.gettempdir(), "sfh-vr-hud")
CDP_URL = "http://127.0.0.1:8080/json"
W, H = 720, 330

DEFAULTS = {
    "x": 0.0, "y": -0.16, "z": -0.5,      # metres, headset space (-z is forward): bottom centre
    "width": 0.17,                         # metres
    "alpha": 0.9,
    "interval": 0.25,                      # seconds between frames
    "flip_x": False, "flip_y": True,       # texture orientation (see Overlay)
}
TICK = 0.05                                # main loop period, seconds

# ---------- OpenVR ----------

VROverlayHandle = ctypes.c_uint64
APP_OVERLAY = 2
HMD = 0
GL_TEXTURE_2D, GL_RGBA, GL_RGBA8, GL_UNSIGNED_BYTE = 0x0DE1, 0x1908, 0x8058, 0x1401
TEXTURE_OPENGL, COLORSPACE_AUTO = 1, 0


class HmdMatrix34(ctypes.Structure):
    _fields_ = [("m", (ctypes.c_float * 4) * 3)]


class Texture(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_void_p), ("eType", ctypes.c_int),
                ("eColorSpace", ctypes.c_int)]


class TextureBounds(ctypes.Structure):
    _fields_ = [("uMin", ctypes.c_float), ("vMin", ctypes.c_float),
                ("uMax", ctypes.c_float), ("vMax", ctypes.c_float)]


FN = ctypes.CFUNCTYPE
SIGS = {
    # index in VR_IVROverlay_FnTable (IVROverlay_028): (restype, argtypes)
    "CreateOverlay": (1, ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p,
                                         ctypes.POINTER(VROverlayHandle)]),
    "DestroyOverlay": (3, ctypes.c_int, [VROverlayHandle]),
    "SetOverlayAlpha": (16, ctypes.c_int, [VROverlayHandle, ctypes.c_float]),
    "SetOverlaySortOrder": (20, ctypes.c_int, [VROverlayHandle, ctypes.c_uint32]),
    "SetOverlayWidthInMeters": (22, ctypes.c_int, [VROverlayHandle, ctypes.c_float]),
    "SetOverlayTransformTrackedDeviceRelative": (35, ctypes.c_int, [
        VROverlayHandle, ctypes.c_uint32, ctypes.POINTER(HmdMatrix34)]),
    "ShowOverlay": (43, ctypes.c_int, [VROverlayHandle]),
    "HideOverlay": (44, ctypes.c_int, [VROverlayHandle]),
    "SetOverlayTextureBounds": (30, ctypes.c_int, [VROverlayHandle,
                                                    ctypes.POINTER(TextureBounds)]),
    "SetOverlayTexture": (60, ctypes.c_int, [VROverlayHandle, ctypes.POINTER(Texture)]),
}
class GlTextures:
    """Desktop GL context without a window (EGL surfaceless; Mesa zink on the Frame) and
    two textures used in turn. SetOverlayTexture copies the texture into SteamVR, so the
    overlay keeps one texture: no blinking and no per-update allocations. (SetOverlayRaw
    allocates a new texture on every call: the overlay blinks, and after ~200 calls SteamVR
    refuses it with EVROverlayError 23.)"""

    def __init__(self):
        egl = ctypes.CDLL("libEGL.so.1")
        self.gl = gl = ctypes.CDLL("libOpenGL.so.0")
        egl.eglGetPlatformDisplay.restype = ctypes.c_void_p
        egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        egl.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        egl.eglCreateContext.restype = ctypes.c_void_p
        egl.eglCreateContext.argtypes = [ctypes.c_void_p] * 4
        egl.eglMakeCurrent.argtypes = [ctypes.c_void_p] * 4
        dpy = egl.eglGetPlatformDisplay(0x31DD, None, None)      # EGL_PLATFORM_SURFACELESS_MESA
        if not dpy or not egl.eglInitialize(dpy, None, None) or not egl.eglBindAPI(0x30A2):
            raise OSError("EGL init failed")
        ctx = egl.eglCreateContext(dpy, None, None, None)       # EGL_KHR_no_config_context
        if not ctx or not egl.eglMakeCurrent(dpy, None, None, ctx):
            raise OSError("EGL context failed")
        self.ids = (ctypes.c_uint * 2)()
        gl.glGenTextures(2, self.ids)
        for tex in self.ids:
            gl.glBindTexture(GL_TEXTURE_2D, tex)
            gl.glTexParameteri(GL_TEXTURE_2D, 0x2801, 0x2601)   # MIN_FILTER = LINEAR
            gl.glTexParameteri(GL_TEXTURE_2D, 0x2800, 0x2601)   # MAG_FILTER = LINEAR
            gl.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        self.next = 0

    def upload(self, rgba):
        tex = self.ids[self.next]
        self.next ^= 1
        self.gl.glBindTexture(GL_TEXTURE_2D, tex)
        self.gl.glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, rgba)
        self.gl.glFinish()
        return Texture(tex, TEXTURE_OPENGL, COLORSPACE_AUTO)


class Overlay:
    def __init__(self, cfg, textures):
        self.textures = textures
        self.lib = ctypes.CDLL(LIB)
        self.lib.VR_InitInternal2.restype = ctypes.c_void_p
        self.lib.VR_InitInternal2.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int,
                                              ctypes.c_char_p]
        self.lib.VR_GetGenericInterface.restype = ctypes.c_void_p
        self.lib.VR_GetGenericInterface.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        err = ctypes.c_int(0)
        self.lib.VR_InitInternal2(ctypes.byref(err), APP_OVERLAY, None)
        if err.value:
            raise RuntimeError(f"VR_InitInternal2 error {err.value}")
        self.fn = self.table(b"FnTable:IVROverlay_028", SIGS)

        self.handle = VROverlayHandle(0)
        self.check("CreateOverlay", b"sfh.vrhud", b"SFH HUD", ctypes.byref(self.handle))
        self.check("SetOverlayWidthInMeters", self.handle, cfg["width"])
        self.check("SetOverlayAlpha", self.handle, cfg["alpha"])
        self.check("SetOverlaySortOrder", self.handle, 200)
        mat = HmdMatrix34()
        for r in range(3):
            for c in range(4):
                mat.m[r][c] = 1.0 if r == c else 0.0
        mat.m[0][3], mat.m[1][3], mat.m[2][3] = cfg["x"], cfg["y"], cfg["z"]
        self.check("SetOverlayTransformTrackedDeviceRelative", self.handle, HMD,
                   ctypes.byref(mat))
        # Texture orientation: GL rows are bottom-up, so SteamVR shows the texture upside down;
        # the bounds flip it back (vr_hud.json flip_x / flip_y to adjust).
        u0, u1 = (1.0, 0.0) if cfg["flip_x"] else (0.0, 1.0)
        v0, v1 = (1.0, 0.0) if cfg["flip_y"] else (0.0, 1.0)
        bounds = TextureBounds(u0, v0, u1, v1)
        self.check("SetOverlayTextureBounds", self.handle, ctypes.byref(bounds))
        self.shown = False

    def table(self, name, sigs):
        err = ctypes.c_int(0)
        table = self.lib.VR_GetGenericInterface(name, ctypes.byref(err))
        if not table or err.value:
            raise RuntimeError(f"{name.decode()} unavailable (error {err.value})")
        ptrs = ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p))
        return {n: FN(res, *args)(ptrs[idx]) for n, (idx, res, args) in sigs.items()}

    def check(self, name, *args):
        rc = self.fn[name](*args)
        if rc:
            raise RuntimeError(f"{name} failed: EVROverlayError {rc}")

    def update(self, rgba):
        texture = self.textures.upload(rgba)
        self.check("SetOverlayTexture", self.handle, ctypes.byref(texture))
        if not self.shown:
            self.check("ShowOverlay", self.handle)
            self.shown = True

    def set_visible(self, visible):
        if not visible:
            self.fn["HideOverlay"](self.handle)
            self.shown = False      # shown again by the next update

    def close(self):
        try:
            self.fn["DestroyOverlay"](self.handle)
            self.lib.VR_ShutdownInternal()
        except Exception:
            pass


# ---------- text rendering (glyph atlas, no per-frame processes) ----------

FONT_SIZE = 27
ADV = 17            # horizontal advance per character, px (Hack is monospace, ~16.3 px at 27)
CELL = 24           # atlas cell width (wider than ADV so nothing is clipped while rendering)
LINE_H = 35
BASELINE = 26       # glyph baseline inside a line, px (all glyphs share it)
X0, Y0 = 16, 12
BG = (0x10, 0x14, 0x18, 199)
GREEN, YELLOW, RED, GREY, WHITE = "5CE65C", "F0D24A", "FF5C5C", "A0A0A0", "FFFFFF"
CHARSET = ("".join(chr(c) for c in range(33, 127))
           + "".join(chr(c) for c in range(0x410, 0x450)) + "Ёё↓↑—·")


class TextRenderer:
    """Glyph masks rendered once by ffmpeg; frames are composed by copying pixel rows."""

    def __init__(self):
        os.makedirs(WORK, exist_ok=True)
        filters = []
        for i, ch in enumerate(CHARSET):
            path = os.path.join(WORK, f"g{i}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(ch)
            filters.append(f"drawtext=fontfile={FONT}:textfile={path}:expansion=none:"
                           f"fontcolor=white:fontsize={FONT_SIZE}:x={i * CELL}:"
                           f"y_align=baseline:y={BASELINE}")
        aw = CELL * len(CHARSET)
        mask = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c=black:s={aw}x{LINE_H}:d=1", "-vf", ",".join(filters),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True, timeout=30).stdout
        if len(mask) != aw * LINE_H:
            raise RuntimeError("glyph atlas has unexpected size")
        # per character: LINE_H rows of ADV alpha values
        self.masks = {}
        for i, ch in enumerate(CHARSET):
            self.masks[ch] = [mask[r * aw + i * CELL: r * aw + i * CELL + ADV]
                              for r in range(LINE_H)]
        self.tinted = {}
        self.luts = {}
        self.blank = bytes(BG) * (W * H)

    def lut(self, colour):
        if colour not in self.luts:
            fg = (int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16))
            table = []
            for a in range(256):
                px = [BG[k] + (fg[k] - BG[k]) * a // 255 for k in range(3)]
                px.append(BG[3] + (255 - BG[3]) * a // 255)
                table.append(bytes(px))
            self.luts[colour] = table
        return self.luts[colour]

    def glyph(self, ch, colour):
        key = (ch, colour)
        if key not in self.tinted:
            lut = self.lut(colour)
            self.tinted[key] = [b"".join(lut[a] for a in row)
                                for row in self.masks.get(ch, self.masks["?"])]
        return self.tinted[key]

    def frame(self, lines):
        """lines: list of lines, each a list of (text, colour) segments. Returns RGBA bytes."""
        buf = bytearray(self.blank)
        row_bytes = W * 4
        max_chars = (W - X0) // ADV
        for i, segments in enumerate(lines):
            y = Y0 + i * LINE_H
            if y + LINE_H > H:
                break
            col = 0
            for text, colour in segments:
                for ch in text:
                    if col >= max_chars:
                        break
                    if ch != " ":
                        rows = self.glyph(ch, colour)
                        off = y * row_bytes + (X0 + col * ADV) * 4
                        for r in rows:
                            buf[off:off + ADV * 4] = r
                            off += row_bytes
                    col += 1
        return bytes(buf)


# ---------- Steam streaming stats over CDP ----------

# EVRLinkType / quality values as used by the Steam UI (steamui sp.js enums)
LINK_ADAPTER, LINK_USB, LINK_WIFI, LINK_WIFI2, LINK_COMBINED = 2, 1, 3, 4, 255
QUALITY = {1: (T("отлично", "excellent"), GREEN), 2: (T("хорошо", "good"), GREEN),
           3: (T("средне", "fair"), YELLOW),
           4: (T("плохо", "poor"), RED), 5: (T("плохо", "poor"), RED)}
STEAM_JS = ("(function(){var s=window.streamingStore&&window.streamingStore.m_vrLinkStatus;"
            "return s?JSON.stringify(s.toObject()):''})()")


class Cdp:
    """Persistent DevTools websocket to Steam's SharedJSContext (stdlib only)."""

    def __init__(self):
        self.sock = None
        self.rest = b""
        self.msg_id = 0

    def connect(self):
        targets = json.load(urllib.request.urlopen(CDP_URL, timeout=1))
        target = next(t for t in targets if t.get("title") == "SharedJSContext")
        host_port, path = target["webSocketDebuggerUrl"][len("ws://"):].split("/", 1)
        host, port = host_port.split(":")
        sock = socket.create_connection((host, int(port)), timeout=1)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                      "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise OSError("websocket handshake failed")
            buf += chunk
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.sock = sock

    def _send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        header = bytes([0x81])
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _exact(self, n):
        while len(self.rest) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OSError("websocket closed")
            self.rest += chunk
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def _recv(self):
        payload = b""
        while True:
            b1, b2 = self._exact(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            payload += self._exact(n)
            if b1 & 0x80:
                return json.loads(payload)

    def evaluate(self, expr):
        try:
            if self.sock is None:
                self.connect()
            self.msg_id += 1
            self._send({"id": self.msg_id, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True}})
            while True:
                msg = self._recv()
                if msg.get("id") == self.msg_id:
                    return msg.get("result", {}).get("result", {}).get("value")
        except (OSError, ValueError, StopIteration, KeyError):
            if self.sock:
                self.sock.close()
            self.sock = None
            return None


def steam_links(cdp):
    """{link type: (p100 ms, loss ratio, quality)} for active links, or None if no stream."""
    raw = cdp.evaluate(STEAM_JS)
    if not raw:
        return None
    try:
        links = json.loads(raw).get("links", [])
    except ValueError:
        return None
    out = {}
    for link in links:
        quality = link.get("quality", 0)
        if quality:
            out[link.get("type")] = (link.get("p100"), link.get("loss_ratio"), quality)
    return out


# ---------- system metrics ----------

def run(cmd, timeout=2):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def field(text, label):
    """First token after `label` in iw output (e.g. 'tx bitrate:' -> '960.7')."""
    pos = text.find(label)
    if pos < 0:
        return None
    rest = text[pos + len(label):].split()
    return rest[0] if rest else None


def iw_link(dev):
    out = run(["iw", "dev", dev, "link"])
    return {"signal": field(out, "signal:"), "tx": field(out, "tx bitrate:"),
            "rx": field(out, "rx bitrate:"), "connected": out.startswith("Connected")}


def iw_station(dev):
    out = run(["iw", "dev", dev, "station", "dump"])
    return {"signal": field(out, "last ack signal:"), "tx": field(out, "tx bitrate:"),
            "rx": field(out, "rx bitrate:"), "connected": out.startswith("Station")}


def iw_channel(dev):
    out = run(["iw", "dev", dev, "info"])
    channel, width = field(out, "channel "), field(out, "width:")
    return f"ch{channel} {width}MHz" if channel else ""


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def phy(value):
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return "?"


def net_bytes():
    out = {}
    with open("/proc/net/dev") as f:
        for line in f.readlines()[2:]:
            name, data = line.split(":", 1)
            fields = data.split()
            out[name.strip()] = (int(fields[0]), int(fields[8]))
    return out


def battery():
    """Capacity of the first power supply of type Battery (Frame: max1720x_bat_*)."""
    base = "/sys/class/power_supply"
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return "?"
    for name in names:
        try:
            with open(os.path.join(base, name, "type")) as f:
                if f.read().strip() != "Battery":
                    continue
            with open(os.path.join(base, name, "capacity")) as f:
                return f.read().strip()
        except OSError:
            continue
    return "?"


def grade(value, good, bad, lower_is_better=True):
    if value is None:
        return GREY
    if lower_is_better:
        return GREEN if value <= good else (YELLOW if value <= bad else RED)
    return GREEN if value >= good else (YELLOW if value >= bad else RED)


# ---------- HUD state ----------

class Hud:
    SLOW_EVERY = 1.0      # iw + Steam stats (Steam itself refreshes ~1/s)
    RATE_WINDOW = 1.0     # traffic averaging window, seconds

    def __init__(self):
        self.cdp = Cdp()
        self.samples = collections.deque()
        self.slow_t = 0.0
        self.chan_t = 0.0
        self.ap = self.wl = {}
        self.links = None
        self.chan = {"wlanap": "", "wlan0": ""}
        self.batt = "?"

    def rates(self, now):
        self.samples.append((now, net_bytes()))
        while len(self.samples) > 2 and now - self.samples[1][0] >= self.RATE_WINDOW:
            self.samples.popleft()
        (t0, a), (t1, b) = self.samples[0], self.samples[-1]
        dt = t1 - t0
        out = {}
        for dev in ("wlanap", "wlan0"):
            if dt <= 0 or dev not in a or dev not in b:
                out[dev] = (None, None)
            else:
                out[dev] = ((b[dev][0] - a[dev][0]) * 8 / dt / 1e6,
                            (b[dev][1] - a[dev][1]) * 8 / dt / 1e6)
        return out

    def refresh_slow(self, now):
        if now - self.slow_t < self.SLOW_EVERY:
            return
        self.slow_t = now
        self.ap = iw_station("wlanap")
        self.wl = iw_link("wlan0")
        self.links = steam_links(self.cdp)
        self.batt = battery()
        if now - self.chan_t > 10:
            self.chan_t = now
            self.chan = {dev: iw_channel(dev) for dev in ("wlanap", "wlan0")}

    def link_lines(self, title, dev, info, rate, steam):
        lines = []
        sig = to_int(info.get("signal"))
        head = [(f"{title} ", WHITE), (f"{self.chan[dev]} ", GREY)]
        if not info.get("connected"):
            lines.append(head + [(T("нет связи", "no link"), RED)])
            return lines
        head.append((f"{sig} {T('дБм', 'dBm')}" if sig is not None else f"? {T('дБм', 'dBm')}",
                     grade(sig, -55, -70, lower_is_better=False)))
        lines.append(head)
        rx, tx = rate
        if steam:
            ping, loss, _ = steam
            loss_pct = (loss or 0) * 100
            lines.append([(T(" пинг ", " ping "), GREY),
                          (f"{ping:.1f} {T('мс', 'ms')}" if ping is not None else "-",
                                              grade(ping, 10, 30)),
                          (T("  потери ", "  loss "), GREY), (f"{loss_pct:.1f}%", grade(loss_pct, 0.5, 2))])
        else:
            lines.append([(T(" в стриме не используется", " not used in stream"), GREY)])
        lines.append([(f" ↓{rx or 0:.1f} ↑{tx or 0:.1f} {T('Мбит/с', 'Mbit/s')}", WHITE),
                      (f"  PHY ↓{phy(info.get('rx'))} ↑{phy(info.get('tx'))}", GREY)])
        return lines

    def collect(self):
        now = time.monotonic()
        rates = self.rates(now)
        self.refresh_slow(now)
        links = self.links
        lines = []
        if links is None:
            lines.append([(T("СТРИМ ", "STREAM "), WHITE), (T("не идёт", "not running"), GREY)])
        else:
            combined = links.get(LINK_COMBINED)
            q_text, q_col = QUALITY.get(combined[2] if combined else 0, ("—", GREY))
            total = sum(r[0] or 0 for r in rates.values())
            lines.append([(T("СТРИМ ", "STREAM "), WHITE), (q_text, q_col),
                          (f"  ↓{total:.1f} {T('Мбит/с', 'Mbit/s')}", WHITE)])
        steam = links or {}
        lines += self.link_lines(T("АДАПТЕР", "ADAPTER"), "wlanap", self.ap, rates["wlanap"],
                                 steam.get(LINK_ADAPTER) or steam.get(LINK_USB))
        lines += self.link_lines("WI-FI", "wlan0", self.wl, rates["wlan0"],
                                 steam.get(LINK_WIFI) or steam.get(LINK_WIFI2))
        lines.append([(f"{T('батарея', 'battery')} {self.batt}%   ", GREY), (time.strftime("%H:%M:%S"), GREY)])
        return lines


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


# ---------- main loop ----------

toggle_requested = False
CONTROL_EVERY = 0.25     # seconds between checks of the Steam UI toggle


class SteamControl:
    """Show/hide switch in the Steam UI (Decky plugin SFH Frame Menu, Quick Settings).
    The plugin bumps window.__sfhHud.toggle in Steam's SharedJSContext; the HUD notices
    the change and reports its state back in window.__sfhHud.visible / .seen, so the
    switch shows the real state. Steam UI restarts reset the counter: only changes count."""

    def __init__(self):
        self.cdp = Cdp()
        self.last = None
        self.t = 0.0

    def poll(self, visible):
        """True when the user flipped the switch since the last poll."""
        now = time.monotonic()
        if now - self.t < CONTROL_EVERY:
            return False
        self.t = now
        js = ("(function(){var s=window.__sfhHud=window.__sfhHud||{toggle:0};"
              f"s.visible={'true' if visible else 'false'};s.seen=Date.now();return s.toggle;}})()")
        value = self.cdp.evaluate(js)
        if not isinstance(value, int):
            self.last = None
            self.t = now + 3        # Steam UI not reachable: don't block the loop every tick
            return False
        changed = self.last is not None and value != self.last
        self.last = value
        return changed


def on_sigusr1(signum, frame):
    """`systemctl --user kill -s USR1 sfh-vr-hud` toggles the HUD (SFH button)."""
    global toggle_requested
    toggle_requested = True


# SteamVR must be started by Steam (vrserver -waitformonitor -ipccontrolfilepath ...).
# VR_Init as an overlay app starts SteamVR itself when it is not running; at boot that
# raced Steam, Steam could not start its VR shell and the headset stayed on a blue screen.
# So the overlay connects only after Steam's SteamVR has been up for a while.
STEAMVR_PROCESSES = ("vrserver", "vrcompositor", "vrdashboard")
STEAMVR_SETTLE = 20                        # seconds all of them must be running


def running_processes():
    names = set()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                names.add(f.read().strip())
        except OSError:
            pass
    return names


class SteamVrWatch:
    def __init__(self):
        self.since = None

    def ready(self):
        names = running_processes()
        if all(p in names for p in STEAMVR_PROCESSES):
            if self.since is None:
                self.since = time.monotonic()
            return time.monotonic() - self.since >= STEAMVR_SETTLE
        self.since = None
        return False


def main():
    global toggle_requested
    signal.signal(signal.SIGUSR1, on_sigusr1)
    cfg = load_config()
    text = TextRenderer()
    textures = GlTextures()
    hud = Hud()
    control = SteamControl()
    steamvr = SteamVrWatch()
    overlay = None
    visible = False                        # hidden until shown from SFH or the Decky plugin
    next_frame = 0.0
    while True:
        try:
            if overlay is None:
                if not steamvr.ready():
                    time.sleep(2)
                    continue
                overlay = Overlay(cfg, textures)
                print("overlay created", flush=True)
            if control.poll(visible) or toggle_requested:
                toggle_requested = False
                visible = not visible
                overlay.set_visible(visible)
                next_frame = 0.0
                print("shown" if visible else "hidden", flush=True)
            now = time.monotonic()
            if visible and now >= next_frame:
                next_frame = now + cfg["interval"]
                overlay.update(text.frame(hud.collect()))
        except RuntimeError as e:
            print(f"VR not ready: {e}", flush=True)
            if overlay:
                overlay.close()
            overlay = None
            steamvr.since = None           # SteamVR may be restarting: settle again
            time.sleep(5)
            continue
        except Exception as e:  # keep the HUD alive on transient tool errors
            print(f"update error: {e!r}", flush=True)
        time.sleep(TICK)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
