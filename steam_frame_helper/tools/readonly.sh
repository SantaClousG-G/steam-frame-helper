#!/bin/bash
# SteamOS read-only root filesystem toggle.
# Usage: readonly.sh status | install (unlock: writable) | remove (lock)
# install/remove require root. status works without root: steamos-readonly status
# needs root, so as a user the btrfs "ro" property of / is read directly.

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

readonly_state() {
    local s
    s="$(steamos-readonly status 2>/dev/null)"
    if [ -n "$s" ]; then
        echo "$s"
        return
    fi
    case "$(btrfs property get -ts / ro 2>/dev/null)" in
        ro=false) echo "disabled" ;;
        ro=true) echo "enabled" ;;
    esac
}

case "${1:-status}" in
    status)
        s="$(readonly_state)"
        if [ "$s" = "disabled" ]; then
            echo "installed=1"
            echo "info=$(t "Системный раздел доступен для записи" "System partition is writable")"
        else
            echo "installed=0"
            echo "info=$(t "Системный раздел только для чтения (${s:-неизвестно})" "System partition is read-only (${s:-unknown})")"
        fi
        ;;
    install)
        steamos-readonly disable
        ;;
    remove)
        steamos-readonly enable
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
