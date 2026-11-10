#!/usr/bin/env python3
"""Queue files and folders on Steam Frame for the PC agent (Downloads\\SteamFrame).

The PC agent (pc/screenshot_sync.ps1) polls the Frame over SSH every few seconds,
streams everything in the queue folder to the PC and deletes it here.
Items are hard-linked into the queue (no extra space on the same filesystem),
copied otherwise.

Usage:
  to_pc.py add <path> [path ...]
  to_pc.py list          -> TSV: name, size in bytes
  to_pc.py clear
  to_pc.py status        -> agent heartbeat age in seconds (-1 if never)
Runs as the user.
"""

import os
import shutil
import sys
import time

STATE = os.path.expanduser("~/.local/share/steam_frame_helper")
QUEUE = os.path.join(STATE, "to-pc")
HEARTBEAT = os.path.join(STATE, "pc_heartbeat")


def unique_target(name):
    target = os.path.join(QUEUE, name)
    stem, ext = os.path.splitext(name)
    n = 1
    while os.path.lexists(target):
        target = os.path.join(QUEUE, f"{stem} ({n}){ext}")
        n += 1
    return target


def link_tree(src, dst):
    """Hard-link a directory tree; fall back to copying across filesystems."""
    try:
        shutil.copytree(src, dst, copy_function=os.link, symlinks=True)
    except OSError:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, symlinks=True)


def add(paths):
    os.makedirs(QUEUE, exist_ok=True)
    for p in paths:
        p = os.path.abspath(p.rstrip("/"))
        if not os.path.exists(p):
            print(f"Нет такого пути: {p}", file=sys.stderr)
            continue
        # A part file first, renamed when complete: the agent never sees half an item.
        target = unique_target(os.path.basename(p))
        part = os.path.join(QUEUE, ".part-" + os.path.basename(target))
        if os.path.isdir(p):
            link_tree(p, part)
        else:
            try:
                os.link(p, part)
            except OSError:
                shutil.copy2(p, part)
        os.rename(part, target)
        print(f"В очереди: {os.path.basename(target)}")


def size_of(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "list"
    if cmd == "add" and len(args) > 1:
        add(args[1:])
    elif cmd == "list":
        if os.path.isdir(QUEUE):
            for name in sorted(os.listdir(QUEUE)):
                if not name.startswith(".part-"):
                    print(f"{name}\t{size_of(os.path.join(QUEUE, name))}")
    elif cmd == "clear":
        shutil.rmtree(QUEUE, ignore_errors=True)
        os.makedirs(QUEUE, exist_ok=True)
    elif cmd == "status":
        age = int(time.time() - os.path.getmtime(HEARTBEAT)) if os.path.exists(HEARTBEAT) else -1
        print(age)
    else:
        print(__doc__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
