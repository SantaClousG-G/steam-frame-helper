#!/bin/bash
# The Plasma session ends when the RDP client disconnects.
# xrdp keeps a disconnected session running (so the next connection gets the same desktop),
# which leaves Plasma working in the background for days: its programs use memory and battery,
# and its power manager dims the headset's screen. This makes xrdp end a session a minute after
# its client disconnects (a minute lets a dropped connection come back to the same desktop).
# Sets KillDisconnected / DisconnectedTimeLimit in /etc/xrdp/sesman.ini and makes the running
# sesman reload it (SIGHUP to its main process only: open sessions stay as they are).
# Usage: rdp_logout.sh status | install | remove      (install/remove: root)

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

INI=/etc/xrdp/sesman.ini
GRACE=60

# KillDisconnected's value from the ini ("" when missing)
kill_value() {
    local line value=""
    [ -r "$INI" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in KillDisconnected=*) value="${line#KillDisconnected=}" ;; esac
    done < "$INI"
    printf '%s' "$value"
}

# writes the two settings, keeping every other line (and the file's owner and mode)
set_values() {
    local kill="$1" limit="$2" tmp line
    tmp="$(mktemp)"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            KillDisconnected=*) printf 'KillDisconnected=%s\n' "$kill" ;;
            DisconnectedTimeLimit=*) printf 'DisconnectedTimeLimit=%s\n' "$limit" ;;
            *) printf '%s\n' "$line" ;;
        esac
    done < "$INI" > "$tmp"
    cat "$tmp" > "$INI"
    rm -f "$tmp"
    systemctl kill --kill-whom=main -s HUP xrdp-sesman.service 2>/dev/null
}

case "${1:-status}" in
    status)
        if [ ! -f "$INI" ]; then
            echo "installed=0"
            echo "info=$(t "xrdp не установлен" "xrdp is not installed")"
            exit 0
        fi
        case "$(kill_value)" in
            true|1|yes)
                echo "installed=1"
                echo "info=$(t "Сеанс Plasma закрывается через минуту после отключения RDP" "The Plasma session ends a minute after RDP disconnects")"
                ;;
            *)
                echo "installed=0"
                echo "info=$(t "После закрытия окна RDP сеанс Plasma продолжает работать в фоне" "After the RDP window is closed, the Plasma session keeps running in the background")"
                ;;
        esac
        ;;
    install)
        [ -f "$INI" ] || { echo "$(t "xrdp не установлен" "xrdp is not installed")" >&2; exit 1; }
        set_values true "$GRACE"
        echo "$(t "Готово: сеанс закроется через минуту после отключения. Уже открытые сеансы закроются после следующего отключения." "Done: a session ends a minute after disconnecting. Sessions already open end after their next disconnect.")"
        ;;
    remove)
        [ -f "$INI" ] || exit 0
        set_values false 0
        echo "$(t "Сеансы снова остаются после отключения." "Sessions stay after disconnecting again.")"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
