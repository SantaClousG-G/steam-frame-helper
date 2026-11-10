#!/bin/bash
# Wi-Fi power saving for Steam Frame.
# Usage: wifi.sh status | install (power save OFF) | remove (power save ON)
# install/remove require root.
#
# Valve ships wifi.powersave=2 (off) by default. "remove" adds an override
# that turns power saving on (battery over latency); "install" drops it.

set -u

OVERRIDE=/etc/NetworkManager/conf.d/99-zz-sfh-wifi-powersave.conf

ifaces() {
    iw dev | awk '/Interface/ { name = $2 } /type managed/ { print name }'
}

state() {
    local i
    for i in $(ifaces); do
        iw dev "$i" get power_save | awk '{ print $3 }'
        return
    done
}

apply() {
    local i
    for i in $(ifaces); do
        iw dev "$i" set power_save "$1"
    done
}

case "${1:-status}" in
    status)
        s="$(state)"
        if [ "$s" = "off" ]; then
            echo "installed=1"
            echo "info=Энергосбережение выключено (меньше задержка при стриминге)"
        else
            echo "installed=0"
            echo "info=Энергосбережение включено (${s:-нет Wi-Fi})"
        fi
        ;;
    install)
        rm -f "$OVERRIDE"
        apply off
        ;;
    remove)
        printf '[connection]\nwifi.powersave = 3\n' > "$OVERRIDE"
        apply on
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
