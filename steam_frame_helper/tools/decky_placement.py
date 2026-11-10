#!/usr/bin/env python3
"""Where the SFH Frame Menu plugin shows Decky on Steam Frame: the left menu, the Quick
Settings popup, or both. The plugin keeps the choice in Steam's localStorage and exposes
window.__sfhPlacement; this script reads / changes it over Steam's CEF debugger.

Usage: decky_placement.py get                 -> menu=1|0, qam=1|0 (key=value lines)
       decky_placement.py set <menu> <qam>     (each 1 or 0)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decky_open import CDP, find_target  # noqa: E402


def evaluate(js):
    ws_url = find_target()
    if not ws_url:
        raise RuntimeError("Steam UI not found")
    return CDP(ws_url).evaluate(js)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "get"
    if cmd == "get":
        js = "JSON.stringify(window.__sfhPlacement ? window.__sfhPlacement.get() : null)"
    elif cmd == "set" and len(sys.argv) == 4:
        value = {"menu": sys.argv[2] == "1", "qam": sys.argv[3] == "1"}
        js = ("JSON.stringify(window.__sfhPlacement ? "
              f"window.__sfhPlacement.set({json.dumps(value)}) : null)")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        raw = evaluate(js)
    except (OSError, ValueError, ConnectionError, RuntimeError) as e:
        print(f"error={e}")
        return 1
    value = json.loads(raw) if raw else None
    if not value:
        print("error=plugin-not-loaded")
        return 1
    print(f"menu={1 if value.get('menu') else 0}")
    print(f"qam={1 if value.get('qam') else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
