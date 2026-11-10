#!/bin/bash
# SteamOS read-only root filesystem toggle.
# Usage: readonly.sh status | install (unlock: writable) | remove (lock)
# All commands require root (steamos-readonly status needs it too).

set -u

case "${1:-status}" in
    status)
        s="$(steamos-readonly status 2>/dev/null)"
        if [ "$s" = "disabled" ]; then
            echo "installed=1"
            echo "info=Системный раздел доступен для записи"
        else
            echo "installed=0"
            echo "info=Системный раздел только для чтения (${s:-неизвестно})"
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
