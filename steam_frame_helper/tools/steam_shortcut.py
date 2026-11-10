#!/usr/bin/env python3
"""Manage the "Decky" non-Steam shortcut in the Steam library.

Steam rewrites shortcuts.vdf on exit, so Steam is stopped while the file is
changed and started again afterwards (systemd user unit steam.service).

Usage: steam_shortcut.py status | add | remove
"""

import binascii
import glob
import os
import shutil
import struct
import subprocess
import sys

STEAM = os.path.expanduser("~/.local/share/Steam")
TOOLS = os.path.dirname(os.path.abspath(__file__))
NAME = "Decky"
EXE = f'"{os.path.join(TOOLS, "decky_open.py")}"'
START_DIR = f'"{TOOLS}"'
ICON = os.path.join(os.path.dirname(TOOLS), "assets", "decky.png")

T_MAP, T_STR, T_INT, T_U64, T_END = 0x00, 0x01, 0x02, 0x07, 0x08


# ---------- binary VDF ----------

def _cstr(data, pos):
    end = data.index(b"\x00", pos)
    return data[pos:end].decode("utf-8", "replace"), end + 1


def _parse_map(data, pos):
    out = {}
    while True:
        t = data[pos]
        pos += 1
        if t == T_END:
            return out, pos
        key, pos = _cstr(data, pos)
        if t == T_MAP:
            out[key], pos = _parse_map(data, pos)
        elif t == T_STR:
            out[key], pos = _cstr(data, pos)
        elif t == T_INT:
            out[key] = ("i", struct.unpack_from("<i", data, pos)[0])
            pos += 4
        elif t == T_U64:
            out[key] = ("q", struct.unpack_from("<Q", data, pos)[0])
            pos += 8
        else:
            raise ValueError(f"Unknown VDF type {t:#x} at {pos}")


def _dump_map(obj):
    out = b""
    for key, value in obj.items():
        k = key.encode() + b"\x00"
        if isinstance(value, dict):
            out += bytes([T_MAP]) + k + _dump_map(value)
        elif isinstance(value, str):
            out += bytes([T_STR]) + k + value.encode() + b"\x00"
        elif value[0] == "i":
            out += bytes([T_INT]) + k + struct.pack("<i", value[1])
        else:
            out += bytes([T_U64]) + k + struct.pack("<Q", value[1])
    return out + bytes([T_END])


def load(path):
    if not os.path.exists(path):
        return {"shortcuts": {}}
    with open(path, "rb") as f:
        data = f.read()
    root, _ = _parse_map(data, 0)
    root.setdefault("shortcuts", {})
    return root


def save(path, root):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and not os.path.exists(path + ".sfh-bak"):
        shutil.copy2(path, path + ".sfh-bak")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_dump_map(root) + bytes([T_END]))
    os.replace(tmp, path)


# ---------- shortcuts ----------

def shortcut_files():
    return sorted(glob.glob(os.path.join(STEAM, "userdata", "*", "config")))


def find(shortcuts):
    for idx, entry in shortcuts.items():
        if entry.get("AppName", entry.get("appname")) == NAME:
            return idx
    return None


def make_entry():
    appid = binascii.crc32((EXE + NAME).encode()) | 0x80000000
    return {
        "appid": ("i", struct.unpack("<i", struct.pack("<I", appid))[0]),
        "AppName": NAME,
        "Exe": EXE,
        "StartDir": START_DIR,
        "icon": ICON if os.path.exists(ICON) else "",
        "ShortcutPath": "",
        "LaunchOptions": "",
        "IsHidden": ("i", 0),
        "AllowDesktopConfig": ("i", 1),
        "AllowOverlay": ("i", 1),
        "OpenVR": ("i", 0),
        "Devkit": ("i", 0),
        "DevkitGameID": "",
        "DevkitOverrideAppID": ("i", 0),
        "LastPlayTime": ("i", 0),
        "FlatpakAppID": "",
        "tags": {},
    }


def steam_running():
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", "steam.service"]).returncode == 0


def change(add):
    was_running = steam_running()
    if was_running:
        subprocess.run(["systemctl", "--user", "stop", "steam.service"], check=True)
    try:
        for cfg in shortcut_files():
            path = os.path.join(cfg, "shortcuts.vdf")
            root = load(path)
            sc = root["shortcuts"]
            idx = find(sc)
            if add and idx is None:
                sc[str(len(sc))] = make_entry()
            elif not add and idx is not None:
                del sc[idx]
                root["shortcuts"] = {str(i): v for i, v in enumerate(sc.values())}
            else:
                continue
            save(path, root)
    finally:
        if was_running:
            subprocess.run(["systemctl", "--user", "start", "steam.service"], check=True)


def presence():
    """Per userdata config dir: whether the shortcut is there."""
    return [find(load(os.path.join(c, "shortcuts.vdf"))["shortcuts"]) is not None
            for c in shortcut_files()]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(f"installed={1 if any(presence()) else 0}")
        return 0
    if cmd in ("add", "remove"):
        add = cmd == "add"
        # Restarting Steam is disruptive in VR: only do it when something changes.
        if any(p != add for p in presence()):
            change(add)
        return 0
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
