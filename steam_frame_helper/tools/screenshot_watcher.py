#!/usr/bin/env python3
"""Copy new Steam screenshots on Steam Frame.

Watches userdata/*/760/remote/<appid>/screenshots/*.jpg and, depending on
~/.config/steam_frame_helper/screenshots.json:
  local: copies to ~/Pictures/Screenshots
  pc:    copies to the outbox, which the PC agent pulls over SSH and empties
Files are named "<Game>_<steam name>.jpg". Screenshots that existed before the
watcher first ran are not copied.
"""

import glob
import json
import os
import shutil
import time

HOME = os.path.expanduser("~")
STEAM = os.path.join(HOME, ".local/share/Steam")
CONFIG = os.path.join(HOME, ".config/steam_frame_helper/screenshots.json")
STATE_DIR = os.path.join(HOME, ".local/share/steam_frame_helper")
SEEN_FILE = os.path.join(STATE_DIR, "screenshots_seen.json")
OUTBOX = os.path.join(STATE_DIR, "outbox")
LOCAL_DIR = os.path.join(HOME, "Pictures", "Screenshots")
PATTERN = os.path.join(STEAM, "userdata", "*", "760", "remote", "*", "screenshots", "*.jpg")
POLL_SECONDS = 2
SETTLE_SECONDS = 2  # Steam may still be writing a fresh file

# ASCII only, no spaces: names travel through ssh/scp to Windows PowerShell.
SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
KNOWN_APPS = {"250820": "SteamVR"}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def app_name(appid):
    if appid in KNOWN_APPS:
        return KNOWN_APPS[appid]
    manifest = os.path.join(STEAM, "steamapps", f"appmanifest_{appid}.acf")
    try:
        with open(manifest, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split('"')
                if len(parts) >= 4 and parts[1] == "name":
                    name = "".join(c for c in parts[3].replace(" ", "_") if c in SAFE)
                    return name.strip("_.") or appid
    except OSError:
        pass
    return appid


def target_name(path):
    appid = path.split(os.sep)[-3]
    return f"{app_name(appid)}_{os.path.basename(path)}"


def copy(src, dst_dir, name):
    os.makedirs(dst_dir, exist_ok=True)
    tmp = os.path.join(dst_dir, "." + name + ".part")
    shutil.copy2(src, tmp)
    os.replace(tmp, os.path.join(dst_dir, name))


def main():
    seen = set(load_json(SEEN_FILE, []))
    if not os.path.exists(SEEN_FILE):
        seen = set(glob.glob(PATTERN))
        save_json(SEEN_FILE, sorted(seen))
    while True:
        cfg = load_json(CONFIG, {})
        changed = False
        now = time.time()
        for path in sorted(glob.glob(PATTERN)):
            if path in seen:
                continue
            try:
                if now - os.path.getmtime(path) < SETTLE_SECONDS:
                    continue
                name = target_name(path)
                if cfg.get("local"):
                    copy(path, LOCAL_DIR, name)
                if cfg.get("pc"):
                    copy(path, OUTBOX, name)
                print(f"copied {name} local={bool(cfg.get('local'))} pc={bool(cfg.get('pc'))}",
                      flush=True)
            except OSError as e:
                print(f"error {path}: {e}", flush=True)
                continue
            seen.add(path)
            changed = True
        if changed:
            save_json(SEEN_FILE, sorted(seen))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
