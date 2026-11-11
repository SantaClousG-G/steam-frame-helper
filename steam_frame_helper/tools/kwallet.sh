#!/bin/bash
# KDE Wallet password prompt off.
# Chromium (and other apps) open KDE Wallet on start; the wallet asks for its password
# every time. This turns the wallet off (kwalletrc [Wallet] Enabled=false) and makes the
# Chromium flatpak keep its passwords in its own storage (--password-store=basic).
# Passwords saved in the wallet stay there; turning it on again brings them back.
# Usage: kwallet.sh status | install (turn the wallet off) | remove (turn it back on)
# As the user, no root.

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

CHROMIUM_FLAGS="$HOME/.var/app/org.chromium.Chromium/config/chromium-flags.conf"
FLAG="--password-store=basic"

wallet_enabled() {
    [ "$(kreadconfig6 --file kwalletrc --group Wallet --key Enabled --default true 2>/dev/null)" != "false" ]
}

drop_flag() {
    [ -f "$CHROMIUM_FLAGS" ] || return 0
    local tmp line
    tmp="$(mktemp)"
    while IFS= read -r line || [ -n "$line" ]; do
        [ "$line" = "$FLAG" ] || printf '%s\n' "$line"
    done < "$CHROMIUM_FLAGS" > "$tmp"
    if [ -s "$tmp" ]; then
        cat "$tmp" > "$CHROMIUM_FLAGS"
    else
        rm -f "$CHROMIUM_FLAGS"
    fi
    rm -f "$tmp"
}

case "${1:-status}" in
    status)
        if wallet_enabled; then
            echo "installed=0"
            echo "info=$(t "KDE Wallet включён: браузер и другие приложения спрашивают его пароль" "KDE Wallet is on: the browser and other apps ask for its password")"
        else
            echo "installed=1"
            echo "info=$(t "KDE Wallet выключен: пароль кошелька не спрашивается" "KDE Wallet is off: no wallet password prompt")"
        fi
        ;;
    install)
        kwriteconfig6 --file kwalletrc --group Wallet --key Enabled false
        mkdir -p "$(dirname "$CHROMIUM_FLAGS")"
        drop_flag
        echo "$FLAG" >> "$CHROMIUM_FLAGS"
        # a running wallet daemon keeps its old settings
        pkill -x kwalletd6 2>/dev/null
        pkill -x kwalletd5 2>/dev/null
        echo "$(t "KDE Wallet выключен. Перезапустите браузер." "KDE Wallet is off. Restart the browser.")"
        ;;
    remove)
        kwriteconfig6 --file kwalletrc --group Wallet --key Enabled true
        drop_flag
        echo "$(t "KDE Wallet снова включён. Перезапустите браузер." "KDE Wallet is on again. Restart the browser.")"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
