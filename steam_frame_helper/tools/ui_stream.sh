#!/bin/bash
# Steam UI live view server (tools/ui_stream.py) as a transient user unit.
# Usage: ui_stream.sh status | install (start) | remove (stop)
# Runs as the user, no root needed.

set -u

UNIT=sfh-ui-stream
PORT=8091
TOOLS="$(cd "$(dirname "$0")" && pwd)"
TOKEN_FILE="$(dirname "$TOOLS")/ui_stream.token"

ip_addr() {
    ip -4 -o addr show wlan0 2>/dev/null | awk '{ split($4, a, "/"); print a[1]; exit }'
}

case "${1:-status}" in
    status)
        if systemctl --user is-active --quiet "$UNIT"; then
            echo "installed=1"
            echo "info=Открой на ПК: http://$(ip_addr):$PORT/?t=$(cat "$TOKEN_FILE" 2>/dev/null)"
        else
            echo "installed=0"
            echo "info=Выключено (интерфейс Steam в браузере на ПК, игры не видны)"
        fi
        ;;
    install)
        systemctl --user stop "$UNIT" 2>/dev/null
        systemctl --user reset-failed "$UNIT" 2>/dev/null
        systemd-run --user --unit="$UNIT" --description="Steam Frame UI stream" \
            python3 "$TOOLS/ui_stream.py" "$PORT"
        sleep 1
        systemctl --user is-active --quiet "$UNIT"
        ;;
    remove)
        systemctl --user stop "$UNIT"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
