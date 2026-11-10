#!/bin/bash
# Quick system actions for Steam Frame.
# Usage: system.sh restart-steam | reboot | desktop | gamemode
# reboot requires root; the rest run as the user.

set -u

case "${1:-}" in
    restart-steam)
        systemctl --user restart steam.service
        ;;
    reboot)
        systemctl reboot
        ;;
    desktop)
        steamos-session-select plasma
        ;;
    gamemode)
        steamos-session-select gamescope
        ;;
    *)
        echo "Usage: $0 restart-steam | reboot | desktop | gamemode" >&2
        exit 1
        ;;
esac
