#!/bin/bash
# Quick system actions for Steam Frame.
# Usage: system.sh restart-steam | reboot | stop-stream | desktop | gamemode
# reboot requires root; the rest run as the user.
# stop-stream ends PC VR streaming by stopping the Frame's streaming client (vrlink).
# The Steam UI button "Stop streaming" stops working when the Steam UI was reloaded
# during a stream (e.g. Decky restarted): the UI forgets the running session.

set -u
TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

case "${1:-}" in
    restart-steam)
        systemctl --user restart steam.service
        ;;
    reboot)
        systemctl reboot
        ;;
    stop-stream)
        if ! pgrep -f "vrlink -I" >/dev/null; then
            echo "$(t "Трансляция с ПК не идёт" "PC streaming is not running")" >&2
            exit 1
        fi
        pkill -TERM -f "vrlink -I"
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            pgrep -f "vrlink -I" >/dev/null || break
            sleep 0.5
        done
        if pgrep -f "vrlink -I" >/dev/null; then
            echo "$(t "Клиент трансляции не завершился" "The streaming client did not stop")" >&2
            exit 1
        fi
        echo "$(t "Трансляция с ПК прервана" "PC streaming stopped")"
        ;;
    desktop)
        steamos-session-select plasma
        ;;
    gamemode)
        steamos-session-select gamescope
        ;;
    *)
        echo "Usage: $0 restart-steam | reboot | stop-stream | desktop | gamemode" >&2
        exit 1
        ;;
esac
