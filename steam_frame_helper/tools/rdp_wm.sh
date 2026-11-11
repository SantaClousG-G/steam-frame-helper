#!/bin/bash
# Window title bars in RDP (xrdp) sessions.
# xrdp starts Plasma on X11, but SteamOS ships only kwin_wayland: kwin_x11 is missing,
# so the RDP session has no window manager and windows have no title bars (cannot be
# moved, minimized or closed). Plasma starts the window manager named in $KDEWM instead
# of kwin_x11; this sets it to Openbox (part of SteamOS) for xrdp sessions only. The
# in-headset desktop (Wayland) is not affected.
# Usage: rdp_wm.sh status | install | remove      (as the user, no root)

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

ENV_FILE="$HOME/.config/plasma-workspace/env/sfh-rdp-wm.sh"
WM=/usr/bin/openbox

# X displays of running xrdp sessions (Xorg started with the xrdp config)
xrdp_displays() {
    local pid arg display is_xrdp
    for pid in $(pgrep -x Xorg); do
        display=""
        is_xrdp=0
        while IFS= read -r -d '' arg; do
            case "$arg" in
                :[0-9]*) display="$arg" ;;
                xrdp/*) is_xrdp=1 ;;
            esac
        done < "/proc/$pid/cmdline"
        [ "$is_xrdp" = 1 ] && [ -n "$display" ] && echo "$display"
    done
}

case "${1:-status}" in
    status)
        if [ -f "$ENV_FILE" ]; then
            echo "installed=1"
            echo "info=$(t "Окна в RDP с заголовками (Openbox): их можно двигать, сворачивать и закрывать" "Windows in RDP have title bars (Openbox): move, minimize and close them")"
        else
            echo "installed=0"
            echo "info=$(t "В RDP у окон нет заголовков: в SteamOS нет оконного менеджера для X11 (kwin_x11)" "In RDP, windows have no title bars: SteamOS has no X11 window manager (kwin_x11)")"
        fi
        ;;
    install)
        if [ ! -x "$WM" ]; then
            echo "$(t "Openbox не найден в системе" "Openbox is not found on the system")" >&2
            exit 1
        fi
        mkdir -p "$(dirname "$ENV_FILE")"
        cat > "$ENV_FILE" <<EOF
# Steam Frame Helper: Openbox as the window manager of xrdp sessions (no kwin_x11 in SteamOS)
if [ -n "\${XRDP_SESSION:-}" ] && [ ! -x /usr/bin/kwin_x11 ]; then
    export KDEWM=$WM
fi
EOF
        # apply to RDP sessions that are already open
        for display in $(xrdp_displays); do
            DISPLAY="$display" XAUTHORITY="$HOME/.Xauthority" setsid "$WM" --replace \
                >/dev/null 2>&1 < /dev/null &
        done
        echo "$(t "Готово: заголовки окон появятся в RDP (в открытой сессии — сразу)." "Done: window title bars appear in RDP (right away in an open session).")"
        ;;
    remove)
        rm -f "$ENV_FILE"
        echo "$(t "Убрано. Подействует при следующем входе по RDP." "Removed. Takes effect at the next RDP login.")"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
