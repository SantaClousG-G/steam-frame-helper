#!/bin/bash
# Wi-Fi regulatory domain tool for Steam Frame.
# Usage: region.sh status | install <CODE> | remove
# install/remove require root.

set -u

CONF=/etc/conf.d/wireless-regdom
SUPPORTED="DE PL FI NL FR GB US RU"

configured() {
    sed -n 's/^WIRELESS_REGDOM="\(..\)".*/\1/p' "$CONF" | head -n1
}

current() {
    iw reg get | awk '/^phy#/ { p = 1 } p && /^country/ { print substr($2, 1, 2); exit }'
}

is_supported() {
    local c
    for c in $SUPPORTED; do
        [ "$c" = "$1" ] && return 0
    done
    return 1
}

case "${1:-status}" in
    status)
        conf="$(configured)"
        cur="$(current)"
        echo "configured=$conf"
        if [ -n "$conf" ]; then
            echo "installed=1"
            echo "info=Установлен: $conf  ·  сейчас у Wi-Fi: ${cur:-?}"
        else
            echo "installed=0"
            echo "info=Не установлен  ·  сейчас у Wi-Fi: ${cur:-?}"
        fi
        ;;
    install)
        code="${2:-}"
        if ! is_supported "$code"; then
            echo "Unsupported region: $code" >&2
            exit 2
        fi
        [ -f "$CONF.orig" ] || cp "$CONF" "$CONF.orig"
        sed -i 's/^WIRELESS_REGDOM=/#&/' "$CONF"
        if grep -q "^#WIRELESS_REGDOM=\"$code\"" "$CONF"; then
            sed -i "s/^#WIRELESS_REGDOM=\"$code\"/WIRELESS_REGDOM=\"$code\"/" "$CONF"
        else
            echo "WIRELESS_REGDOM=\"$code\"" >> "$CONF"
        fi
        iw reg set "$code"
        ;;
    remove)
        sed -i 's/^WIRELESS_REGDOM=/#&/' "$CONF"
        iw reg set 00
        ;;
    *)
        echo "Usage: $0 status | install <CODE> | remove" >&2
        exit 1
        ;;
esac
