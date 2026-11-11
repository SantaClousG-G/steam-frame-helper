#!/usr/bin/env python3
"""Install an Android APK (+ OBB files) on Steam Frame as a regular Steam library app.

Steam runs Android games through the Lepton compatibility tool (android -> linux).
For a library entry pointing at an .apk, Lepton creates its own container in
compatdata/<shortcut appid>, installs the APK there and mounts OBB files from the
"obb" folder next to the APK (Lepton cannot mount OBBs from the APK folder itself).

Two Lepton runtimes exist: "lepton" (Android 11, SDK 30) and "lepton_14"
(Android 14, SDK 34). APKs whose minSdkVersion is above 30 fail to install on the
first one ("requires newer sdk version"), so "auto" picks Lepton 14 for them.
Steam downloads Lepton 14 on the first launch that needs it.

This tool:
  1. creates ~/Games/<name>/ with app.apk and obb/<original obb names>
     (hard links when the source is on the same filesystem, copies otherwise);
  2. adds a non-Steam shortcut "<name>" whose target is that .apk;
  3. maps the shortcut to the Lepton tool in config.vdf (CompatToolMapping) —
     the same as "Force the use of a specific compatibility tool" in the properties.
Steam is stopped while shortcuts.vdf/config.vdf change and started again afterwards.

Usage:
  android_app.py list
  android_app.py info <app.apk>
  android_app.py install "<name>" <app.apk> [file.obb ...] [--lepton auto|11|14]
  android_app.py remove "<name>" [--purge] (--purge also deletes ~/Games/<name>;
                                            the Lepton container with saves is kept)
  android_app.py lepton14 status | install  (install: steam://install/5181730)
Runs as the user.
"""

import binascii
import os
import re
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import steam_shortcut as sc  # noqa: E402  (binary VDF helpers)

STEAM = os.path.expanduser("~/.local/share/Steam")
GAMES = os.path.expanduser("~/Games")
CONFIG_VDF = os.path.join(STEAM, "config", "config.vdf")
# Lepton's own manifest reader (the one Lepton uses at launch).
APK_INFO = os.path.join(STEAM, "steamapps", "common", "Lepton", "liblepton",
                        "apk_extractor", "bin", "apk-info-extractor")
LEPTON_TOOLS = {"11": ("lepton", 30), "14": ("lepton_14", 34)}
TAG = "SFH Android"


# ---------- text VDF (config.vdf) ----------

TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_text_vdf(text):
    tokens = [m.group(1) if m.group(1) is not None else m.group(2)
              for m in TOKEN.finditer(text)]
    pos = 0

    def parse_map():
        nonlocal pos
        out = {}
        while pos < len(tokens):
            tok = tokens[pos]
            if tok == "}":
                pos += 1
                return out
            key = tok
            pos += 1
            if tokens[pos] == "{":
                pos += 1
                out[key] = parse_map()
            else:
                out[key] = tokens[pos]
                pos += 1
        return out

    return parse_map()


def dump_text_vdf(obj, indent=0):
    tabs = "\t" * indent
    lines = []
    for key, value in obj.items():
        if isinstance(value, dict):
            lines.append(f'{tabs}"{key}"\n{tabs}{{\n{dump_text_vdf(value, indent + 1)}{tabs}}}\n')
        else:
            lines.append(f'{tabs}"{key}"\t\t"{value}"\n')
    return "".join(lines)


def compat_mapping(root):
    node = root
    for key in ("InstallConfigStore", "Software", "Valve", "Steam"):
        node = next((v for k, v in node.items() if k.lower() == key.lower()), None)
        if node is None:
            raise RuntimeError(f"config.vdf: section {key} not found")
    for k in node:
        if k.lower() == "compattoolmapping":
            return node[k]
    node["CompatToolMapping"] = {}
    return node["CompatToolMapping"]


def read_config():
    with open(CONFIG_VDF, encoding="utf-8") as f:
        return parse_text_vdf(f.read())


def write_config(root):
    if not os.path.exists(CONFIG_VDF + ".sfh-bak"):
        shutil.copy2(CONFIG_VDF, CONFIG_VDF + ".sfh-bak")
    tmp = CONFIG_VDF + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(dump_text_vdf(root))
    os.replace(tmp, CONFIG_VDF)


# ---------- APK metadata ----------

def apk_field(apk, field):
    res = subprocess.run([APK_INFO, f"--print-{field}", apk], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""


def apk_info(apk):
    min_sdk = apk_field(apk, "min-sdk-version")
    return {
        "app_id": apk_field(apk, "app-id"),
        "min_sdk": int(min_sdk) if min_sdk.isdigit() else 0,
        "version": apk_field(apk, "app-version"),
    }


def choose_lepton(min_sdk, wanted):
    """Returns (version key, tool name). wanted: auto | 11 | 14."""
    if wanted in LEPTON_TOOLS:
        return wanted, LEPTON_TOOLS[wanted][0]
    key = "14" if min_sdk > LEPTON_TOOLS["11"][1] else "11"
    return key, LEPTON_TOOLS[key][0]


# ---------- helpers ----------

def unsigned_appid(exe, name):
    return binascii.crc32((exe + name).encode()) | 0x80000000


def link_or_copy(src, dst):
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
        return "link"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def steam_stopped(func):
    running = sc.steam_running()
    if running:
        subprocess.run(["systemctl", "--user", "stop", "steam.service"], check=True)
    try:
        func()
    finally:
        if running:
            subprocess.run(["systemctl", "--user", "start", "steam.service"], check=True)


def find_entry(shortcuts, name):
    for idx, entry in shortcuts.items():
        if entry.get("AppName", entry.get("appname")) == name:
            return idx
    return None


# ---------- commands ----------

def cmd_list():
    """TSV: name, apk path, OBB count, size MB, container (0/1), compat tool, appid, log."""
    mapping = compat_mapping(read_config())
    seen = set()
    for cfg in sc.shortcut_files():
        for entry in sc.load(os.path.join(cfg, "shortcuts.vdf"))["shortcuts"].values():
            if TAG not in entry.get("tags", {}).values() or entry["AppName"] in seen:
                continue
            seen.add(entry["AppName"])
            apk = entry["Exe"].strip('"')
            obb_dir = os.path.join(os.path.dirname(apk), "obb")
            obbs = os.listdir(obb_dir) if os.path.isdir(obb_dir) else []
            size = os.path.getsize(apk) if os.path.exists(apk) else 0
            size += sum(os.path.getsize(os.path.join(obb_dir, f)) for f in obbs)
            appid = struct.unpack("<I", struct.pack("<i", entry["appid"][1]))[0]
            container = os.path.isdir(os.path.join(STEAM, "steamapps", "compatdata", str(appid)))
            tool = mapping.get(str(appid), {}).get("name", "?")
            # Lepton writes one log per Steam launch context: steamlaunch-<appid>.
            log = os.path.join(STEAM, "logs", f"lepton-steamlaunch-{appid}.log")
            print("\t".join([entry["AppName"], apk, str(len(obbs)),
                             str(size // (1024 * 1024)), "1" if container else "0", tool,
                             str(appid), log if os.path.exists(log) else ""]))


def cmd_info(apk):
    info = apk_info(apk)
    key, tool = choose_lepton(info["min_sdk"], "auto")
    print(f"app_id={info['app_id']}")
    print(f"min_sdk={info['min_sdk']}")
    print(f"version={info['version']}")
    print(f"lepton={key}")
    print(f"tool={tool}")


def cmd_install(name, apk, obbs, wanted="auto"):
    if not apk.endswith(".apk") or not os.path.isfile(apk):
        sys.exit(f"Not an APK: {apk}")
    info = apk_info(apk)
    key, tool = choose_lepton(info["min_sdk"], wanted)
    if info["min_sdk"] > LEPTON_TOOLS[key][1]:
        sys.exit(f"APK requires SDK {info['min_sdk']}, Lepton {key} provides SDK "
                 f"{LEPTON_TOOLS[key][1]}: choose Lepton 14 or auto")
    print(f"APK {info['app_id']} minSdk {info['min_sdk']} -> Lepton {key} ({tool})")

    folder = os.path.join(GAMES, name)
    os.makedirs(os.path.join(folder, "obb"), exist_ok=True)
    target_apk = os.path.join(folder, "app.apk")
    print(f"APK: {link_or_copy(apk, target_apk)} -> {target_apk}")
    for obb in obbs:
        dst = os.path.join(folder, "obb", os.path.basename(obb))
        print(f"OBB: {link_or_copy(obb, dst)} -> {dst}")

    exe = f'"{target_apk}"'
    appid = unsigned_appid(exe, name)

    def change():
        for cfg in sc.shortcut_files():
            path = os.path.join(cfg, "shortcuts.vdf")
            root = sc.load(path)
            shortcuts = root["shortcuts"]
            idx = find_entry(shortcuts, name)
            entry = {
                "appid": ("i", struct.unpack("<i", struct.pack("<I", appid))[0]),
                "AppName": name,
                "Exe": exe,
                "StartDir": f'"{folder}"',
                "icon": "",
                "ShortcutPath": "",
                "LaunchOptions": "",
                "IsHidden": ("i", 0),
                "AllowDesktopConfig": ("i", 1),
                "AllowOverlay": ("i", 1),
                "OpenVR": ("i", 1),
                "Devkit": ("i", 0),
                "DevkitGameID": "",
                "DevkitOverrideAppID": ("i", 0),
                "LastPlayTime": ("i", 0),
                "FlatpakAppID": "",
                "tags": {"0": TAG},
            }
            shortcuts[idx if idx is not None else str(len(shortcuts))] = entry
            sc.save(path, root)

        root = read_config()
        compat_mapping(root)[str(appid)] = {"name": tool, "config": "", "priority": "250"}
        write_config(root)

    steam_stopped(change)
    print(f"Installed: {name} (shortcut appid {appid}, compat tool {tool})")


def cmd_remove(name, purge=False):
    if purge:
        folder = os.path.join(GAMES, name)
        # Only folders this tool created: ~/Games/<name> with app.apk inside.
        if os.path.isfile(os.path.join(folder, "app.apk")):
            shutil.rmtree(folder)
            print(f"Deleted {folder}")

    def change():
        for cfg in sc.shortcut_files():
            path = os.path.join(cfg, "shortcuts.vdf")
            root = sc.load(path)
            idx = find_entry(root["shortcuts"], name)
            if idx is None:
                continue
            entry = root["shortcuts"].pop(idx)
            root["shortcuts"] = {str(i): v for i, v in enumerate(root["shortcuts"].values())}
            sc.save(path, root)
            appid = struct.unpack("<I", struct.pack("<i", entry["appid"][1]))[0]
            cfg_root = read_config()
            compat_mapping(cfg_root).pop(str(appid), None)
            write_config(cfg_root)

    steam_stopped(change)
    print(f"Removed shortcut: {name}")


# ---------- Lepton 14 runtime ----------

LEPTON14_APPID = 5181730          # Steam tool "Lepton 14" (Android 14, SDK 34)


def library_dirs():
    """steamapps folders of all Steam libraries (internal storage, SD card)."""
    dirs = [os.path.join(STEAM, "steamapps")]
    try:
        with open(os.path.join(STEAM, "steamapps", "libraryfolders.vdf"), encoding="utf-8") as f:
            for line in f:
                parts = line.split('"')
                if len(parts) >= 4 and parts[1] == "path":
                    path = os.path.join(parts[3].replace("\\\\", "\\"), "steamapps")
                    if path not in dirs:
                        dirs.append(path)
    except OSError:
        pass
    return dirs


def lepton14_state():
    """installed | downloading | missing (StateFlags 4 = fully installed)."""
    for d in library_dirs():
        manifest = os.path.join(d, f"appmanifest_{LEPTON14_APPID}.acf")
        try:
            with open(manifest, encoding="utf-8") as f:
                for line in f:
                    parts = line.split('"')
                    if len(parts) >= 4 and parts[1] == "StateFlags":
                        return "installed" if parts[3] == "4" else "downloading"
        except OSError:
            continue
    return "missing"


def cmd_lepton14_status():
    print(f"state={lepton14_state()}")


def cmd_lepton14_install():
    """Ask the running Steam client to install the tool (same as steam://install/<appid>)."""
    if lepton14_state() == "installed":
        print("Lepton 14 is already installed")
        return
    subprocess.Popen(["steam", f"steam://install/{LEPTON14_APPID}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    print("Lepton 14: download requested from Steam")


def main():
    args = sys.argv[1:]
    wanted = "auto"
    if "--lepton" in args:
        i = args.index("--lepton")
        wanted = args[i + 1] if i + 1 < len(args) else "auto"
        del args[i:i + 2]
        if wanted not in ("auto", "11", "14"):
            print("--lepton must be auto, 11 or 14", file=sys.stderr)
            return 1
    if args[:1] == ["list"]:
        cmd_list()
    elif args[:1] == ["info"] and len(args) == 2:
        cmd_info(args[1])
    elif args[:1] == ["install"] and len(args) >= 3:
        cmd_install(args[1], args[2], args[3:], wanted)
    elif args[:1] == ["remove"] and len(args) in (2, 3):
        cmd_remove(args[1], purge=args[2:] == ["--purge"])
    elif args == ["lepton14", "status"]:
        cmd_lepton14_status()
    elif args == ["lepton14", "install"]:
        cmd_lepton14_install()
    else:
        print(__doc__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
