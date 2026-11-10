#!/bin/bash
# VR HUD (network / streaming stats overlay) for Steam Frame Helper.
# Usage: vr_hud.sh status | install | remove | toggle
#   install: user service sfh-vr-hud, started now and at every login
#   toggle:  show / hide the HUD (same as clicking both thumbsticks)
# Runs as the user.

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
UNIT=sfh-vr-hud.service
UNIT_FILE="$HOME/.config/systemd/user/$UNIT"

write_unit() {
    mkdir -p "$(dirname "$UNIT_FILE")"
    cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Steam Frame Helper: VR HUD with network stats

[Service]
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $TOOLS/vr_hud.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
}

case "${1:-status}" in
    status)
        active="$(systemctl --user is-active "$UNIT" 2>/dev/null)"
        if [ -f "$UNIT_FILE" ] && systemctl --user is-enabled "$UNIT" >/dev/null 2>&1; then
            echo "installed=1"
            echo "info=Включён (автозапуск)  ·  служба: $active  ·  показать/скрыть: кнопка справа"
        else
            echo "installed=0"
            echo "info=Окно со статистикой сети и стрима внизу по центру поля зрения"
        fi
        ;;
    install)
        # a test copy may run as a transient unit with the same name
        systemctl --user stop "$UNIT" >/dev/null 2>&1
        systemctl --user reset-failed "$UNIT" >/dev/null 2>&1
        write_unit
        if ! systemctl --user enable --now "$UNIT" 2>&1; then
            echo "не удалось включить службу $UNIT" >&2
            exit 1
        fi
        # give it a moment: a crash right at start shows up as "activating" (auto-restart)
        sleep 2
        state="$(systemctl --user is-active "$UNIT" 2>/dev/null)"
        if [ "$state" != active ]; then
            echo "служба $UNIT не работает (состояние: $state). Журнал:" >&2
            journalctl --user -u "$UNIT" -n 15 --no-pager -o cat >&2
            exit 1
        fi
        echo "VR HUD включён (автозапуск)."
        ;;
    remove)
        systemctl --user disable --now "$UNIT" >/dev/null 2>&1
        rm -f "$UNIT_FILE"
        systemctl --user daemon-reload
        systemctl --user reset-failed "$UNIT" >/dev/null 2>&1
        echo "VR HUD выключен."
        ;;
    toggle)
        systemctl --user kill -s USR1 "$UNIT" 2>/dev/null || { echo "VR HUD не запущен" >&2; exit 1; }
        ;;
    *)
        echo "Usage: $0 status | install | remove | toggle" >&2
        exit 1
        ;;
esac
