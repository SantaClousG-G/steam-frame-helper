#!/usr/bin/env python3
"""Manage installed Decky plugins (mirrors decky-loader v3.3 backend logic).

Usage (root):
  decky_plugins.py list                 -> TSV: folder name version disabled(0/1) latest
  decky_plugins.py enable|disable <folder>
  decky_plugins.py update <folder>
  decky_plugins.py remove <folder>

Decky keeps loader.json in memory and rewrites it, so the service is stopped
while settings or plugin files change and started again afterwards.
"""

import hashlib
import io
import json
import os
import pwd
import shutil
import subprocess
import sys
import urllib.request
import zipfile

USER = os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name
HOME = pwd.getpwnam(USER).pw_dir
HOMEBREW = os.path.join(HOME, "homebrew")
PLUGINS = os.path.join(HOMEBREW, "plugins")
SETTINGS = os.path.join(HOMEBREW, "settings", "loader.json")
VERSION_FILE = os.path.join(HOMEBREW, "services", ".loader.version")
DEFAULT_STORE = "https://plugins.deckbrew.xyz/plugins"
TESTING_STORE = "https://testing.deckbrew.xyz/plugins"


# ---------- settings ----------

def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp, SETTINGS)


def store_url(settings):
    channel = settings.get("store", 0)
    if channel == 1:
        return TESTING_STORE
    if channel == 2:
        return settings.get("store-url") or DEFAULT_STORE
    return DEFAULT_STORE


def loader_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "v3.3.1"


# ---------- plugins ----------

def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def installed():
    out = []
    if not os.path.isdir(PLUGINS):
        return out
    for folder in sorted(os.listdir(PLUGINS)):
        base = os.path.join(PLUGINS, folder)
        meta = read_json(os.path.join(base, "plugin.json"))
        if not meta:
            continue
        pkg = read_json(os.path.join(base, "package.json"))
        out.append({
            "folder": folder,
            "name": meta.get("name", folder),
            "version": pkg.get("version", "?"),
            "root": "root" in meta.get("flags", []),
        })
    return out


def plugin_by_folder(folder):
    for p in installed():
        if p["folder"] == folder:
            return p
    sys.exit(f"Плагин не найден: {folder}")


def fetch_store(settings):
    req = urllib.request.Request(store_url(settings),
                                 headers={"X-Decky-Version": loader_version()})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def latest_versions(settings):
    """Plugin name -> newest store version dict."""
    try:
        store = fetch_store(settings)
    except (OSError, ValueError):
        return {}
    out = {}
    for entry in store:
        versions = entry.get("versions") or []
        if versions:
            out[entry["name"]] = max(versions, key=lambda v: v.get("created", ""))
    return out


# ---------- service ----------

def service(action):
    subprocess.run(["systemctl", action, "plugin_loader"], check=False)


def with_service_stopped(func):
    service("stop")
    try:
        func()
    finally:
        service("start")


# ---------- install helpers (as in decky_loader/browser.py) ----------

def chown(path, user, recursive=False):
    pw = pwd.getpwnam(user)
    paths = [path]
    if recursive:
        for root, dirs, files in os.walk(path):
            paths += [os.path.join(root, n) for n in dirs + files]
    for p in paths:
        os.lchown(p, pw.pw_uid, pw.pw_gid)


def set_permissions(plugin_dir, root_plugin):
    chown(plugin_dir, "root" if root_plugin else USER, recursive=True)
    chown(plugin_dir, "root")
    os.chmod(plugin_dir, 0o755)
    meta = os.path.join(plugin_dir, "plugin.json")
    chown(meta, "root")
    os.chmod(meta, 0o755)


def download(url, sha256):
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if sha256 and digest != sha256:
        sys.exit(f"SHA-256 не совпал для {url}")
    return data


def fetch_remote_binaries(plugin_dir):
    pkg = read_json(os.path.join(plugin_dir, "package.json"))
    binaries = pkg.get("remote_binary") or []
    if not binaries:
        return
    bin_dir = os.path.join(plugin_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    for b in binaries:
        target = os.path.join(bin_dir, b["name"])
        with open(target, "wb") as f:
            f.write(download(b["url"], b["sha256hash"]))
        os.chmod(target, 0o755)


def install_zip(data, old_folder):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        tops = {n.split("/", 1)[0] for n in z.namelist() if n.count("/") == 1 and n.endswith("/plugin.json")}
        if len(tops) != 1:
            sys.exit("В архиве плагина нет единственного plugin.json")
        new_folder = tops.pop()
        shutil.rmtree(os.path.join(PLUGINS, old_folder), ignore_errors=True)
        z.extractall(PLUGINS)
    plugin_dir = os.path.join(PLUGINS, new_folder)
    meta = read_json(os.path.join(plugin_dir, "plugin.json"))
    fetch_remote_binaries(plugin_dir)
    set_permissions(plugin_dir, "root" in meta.get("flags", []))


# ---------- commands ----------

def cmd_list():
    settings = load_settings()
    disabled = set(settings.get("disabled_plugins", []))
    latest = latest_versions(settings)
    for p in installed():
        new = latest.get(p["name"], {}).get("name", "")
        if new == p["version"]:
            new = ""
        print("\t".join([p["folder"], p["name"], p["version"],
                         "1" if p["name"] in disabled else "0", new]))


def cmd_toggle(folder, disable):
    p = plugin_by_folder(folder)

    def change():
        settings = load_settings()
        names = [n for n in settings.get("disabled_plugins", []) if n != p["name"]]
        if disable:
            names.append(p["name"])
        settings["disabled_plugins"] = names
        save_settings(settings)

    with_service_stopped(change)
    print(f"{p['name']}: {'отключён' if disable else 'включён'}")


def cmd_update(folder):
    p = plugin_by_folder(folder)
    version = latest_versions(load_settings()).get(p["name"])
    if not version:
        sys.exit(f"{p['name']} не найден в магазине")
    data = download(version["artifact"], version.get("hash", ""))
    with_service_stopped(lambda: install_zip(data, folder))
    print(f"{p['name']}: обновлён до {version['name']}")


def cmd_remove(folder):
    p = plugin_by_folder(folder)

    def change():
        shutil.rmtree(os.path.join(PLUGINS, folder))
        settings = load_settings()
        for key in ("pluginOrder", "disabled_plugins"):
            if key in settings:
                settings[key] = [n for n in settings[key] if n != p["name"]]
        save_settings(settings)

    with_service_stopped(change)
    print(f"{p['name']}: удалён")


def main():
    args = sys.argv[1:] or ["list"]
    cmd = args[0]
    if cmd == "list":
        cmd_list()
    elif cmd in ("enable", "disable") and len(args) == 2:
        cmd_toggle(args[1], cmd == "disable")
    elif cmd == "update" and len(args) == 2:
        cmd_update(args[1])
    elif cmd == "remove" and len(args) == 2:
        cmd_remove(args[1])
    else:
        print(__doc__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
