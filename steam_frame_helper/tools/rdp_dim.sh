#!/bin/bash
# Screen dimming of the Plasma desktop off.
# An RDP (xrdp) session runs Plasma, and its power manager (PowerDevil) dims the screen, turns
# it off after a while without keyboard or mouse input in that session (SteamOS already keeps it
# from suspending). The session keeps running after the RDP client disconnects and never sees
# VR input, so the headset's display dims from time to time in VR apps. This turns those idle
# actions off in
# ~/.config/powerdevilrc (all power profiles) and makes running PowerDevils reload it.
# The same file is used by the in-headset desktop mode: it does not dim either.
# Usage: rdp_dim.sh status | install (dimming off) | remove (Plasma's defaults back)
# As the user, no root.

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

PROFILES="AC Battery LowBattery"

dimming_off() {
    local profile
    for profile in $PROFILES; do
        [ "$(kreadconfig6 --file powerdevilrc --group "$profile" --group Display --key DimDisplayWhenIdle --default true 2>/dev/null)" = "false" ] || return 1
        [ "$(kreadconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayWhenIdle --default true 2>/dev/null)" = "false" ] || return 1
    done
    return 0
}

# every running PowerDevil (one per Plasma session, each on its session's bus) reads the file again
reload_powerdevil() {
    local pid bus line
    for pid in $(pgrep -u "$(id -u)" -x org_kde_powerde); do   # the process name, cut to 15 characters
        bus=""
        while IFS= read -r -d '' line; do
            case "$line" in DBUS_SESSION_BUS_ADDRESS=*) bus="${line#DBUS_SESSION_BUS_ADDRESS=}" ;; esac
        done < "/proc/$pid/environ" 2>/dev/null
        [ -n "$bus" ] || continue
        DBUS_SESSION_BUS_ADDRESS="$bus" gdbus call --session --dest org.kde.Solid.PowerManagement \
            --object-path /org/kde/Solid/PowerManagement \
            --method org.kde.Solid.PowerManagement.refreshStatus >/dev/null 2>&1
    done
}

case "${1:-status}" in
    status)
        if dimming_off; then
            echo "installed=1"
            echo "info=$(t "Рабочий стол Plasma не затемняет и не выключает экран" "The Plasma desktop does not dim or turn off the screen")"
        else
            echo "installed=0"
            echo "info=$(t "Сеанс Plasma (RDP) затемняет экран шлема, когда в нём долго нет ввода" "A Plasma (RDP) session dims the headset's screen when it has no input for a while")"
        fi
        ;;
    install)
        for profile in $PROFILES; do
            kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key DimDisplayWhenIdle false
            kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayWhenIdle false
        done
        reload_powerdevil
        echo "$(t "Затемнение выключено, работающие сеансы Plasma уже применили настройку." "Dimming is off; running Plasma sessions have applied it.")"
        ;;
    remove)
        for profile in $PROFILES; do
            kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key DimDisplayWhenIdle --delete
            kwriteconfig6 --file powerdevilrc --group "$profile" --group Display --key TurnOffDisplayWhenIdle --delete
        done
        reload_powerdevil
        echo "$(t "Затемнение снова как в Plasma по умолчанию." "Dimming is back to Plasma's defaults.")"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
