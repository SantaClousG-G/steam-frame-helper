#!/bin/bash
# Screenshot copying toggles for Steam Frame Helper.
# Usage: screenshots.sh <local|pc> status | install | remove
#   local: copy to ~/Pictures/Screenshots on the Frame
#   pc:    put into the outbox pulled by the PC agent (Pictures\SteamFrame)
# Runs as the user. The watcher service runs while any target is enabled.

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"
CONFIG="$HOME/.config/steam_frame_helper/screenshots.json"
STATE="$HOME/.local/share/steam_frame_helper"
HEARTBEAT="$STATE/pc_heartbeat"
UNIT=sfh-screenshots.service
UNIT_FILE="$HOME/.config/systemd/user/$UNIT"

target="${1:-}"
cmd="${2:-status}"
case "$target" in
    local | pc) ;;
    *) echo "Usage: $0 <local|pc> status | install | remove" >&2; exit 1 ;;
esac

get() {
    python3 - "$CONFIG" "$1" <<'PY'
import json, sys
try:
    print("1" if json.load(open(sys.argv[1])).get(sys.argv[2]) else "0")
except (OSError, ValueError):
    print("0")
PY
}

set_flag() {
    python3 - "$CONFIG" "$1" "$2" <<'PY'
import json, os, sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
try:
    data = json.load(open(path))
except (OSError, ValueError):
    data = {}
data[key] = value
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(data, open(path + ".tmp", "w"))
os.replace(path + ".tmp", path)
PY
}

write_unit() {
    mkdir -p "$(dirname "$UNIT_FILE")"
    cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Steam Frame Helper: copy new screenshots

[Service]
ExecStart=/usr/bin/python3 $TOOLS/screenshot_watcher.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
}

sync_service() {
    if [ "$(get local)" = 1 ] || [ "$(get pc)" = 1 ]; then
        write_unit
        systemctl --user enable --now "$UNIT" >/dev/null 2>&1
    else
        systemctl --user disable --now "$UNIT" >/dev/null 2>&1
    fi
}

pc_info() {
    local age
    if [ -f "$HEARTBEAT" ]; then
        age=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT") ))
        if [ "$age" -lt 60 ]; then
            echo "$(t "ПК на связи (${age} с назад)" "PC connected (${age} s ago)")"
        else
            echo "$(t "ПК не забирал файлы $((age / 60)) мин — агент на ПК выключен?" "The PC has not picked up files for $((age / 60)) min. Is the PC agent off?")"
        fi
    else
        echo "$(t "агент на ПК ещё не подключался" "the PC agent has not connected yet")"
    fi
}

case "$cmd" in
    status)
        active="$(systemctl --user is-active "$UNIT" 2>/dev/null)"
        if [ "$(get "$target")" = 1 ]; then
            echo "installed=1"
            if [ "$target" = local ]; then
                echo "info=$(t "Копируются в ~/Pictures/Screenshots  ·  служба: $active" "Copied to ~/Pictures/Screenshots  ·  service: $active")"
            else
                queued="$(find "$STATE/outbox" -name '*.jpg' 2>/dev/null | wc -l)"
                echo "info=$(t "Копируются на ПК в Изображения\\SteamFrame  ·  $(pc_info)  ·  в очереди: $queued" "Copied to the PC in Pictures\\SteamFrame  ·  $(pc_info)  ·  queued: $queued")"
            fi
        else
            echo "installed=0"
            if [ "$target" = local ]; then
                echo "info=$(t "Выключено (папка ~/Pictures/Screenshots на Frame)" "Off (folder ~/Pictures/Screenshots on the Frame)")"
            else
                echo "info=$(t "Выключено (папка Изображения\\SteamFrame на ПК)" "Off (folder Pictures\\SteamFrame on the PC)")"
            fi
        fi
        ;;
    install)
        [ "$target" = local ] && mkdir -p "$HOME/Pictures/Screenshots"
        [ "$target" = pc ] && mkdir -p "$STATE/outbox"
        set_flag "$target" 1
        sync_service
        ;;
    remove)
        set_flag "$target" 0
        sync_service
        ;;
    *)
        echo "Usage: $0 <local|pc> status | install | remove" >&2
        exit 1
        ;;
esac
