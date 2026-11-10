#!/bin/bash
# Lets the user scan Wi-Fi without a password prompt in remote (RDP) sessions.
# Plasma's network widget requests org.freedesktop.NetworkManager.wifi.scan every few
# seconds; NetworkManager allows it without a password only in local sessions, so in
# xrdp every request pops up an authentication dialog. The rule allows only this one
# action for the user — other network settings still need authentication.
# Usage: rdp_wifi_scan.sh status | install | remove      (install/remove: root)

set -u

RULE=/etc/polkit-1/rules.d/50-sfh-rdp-wifi-scan.rules
TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}}"
TARGET_USER="${TARGET_USER:-steamos}"

case "${1:-status}" in
    status)
        if [ -f "$RULE" ]; then
            echo "installed=1"
            echo "info=Сканирование Wi-Fi в RDP без запроса пароля (только это действие)"
        else
            echo "installed=0"
            echo "info=В RDP виджет сети Plasma каждые ~10 с запрашивает пароль для сканирования Wi-Fi"
        fi
        ;;
    install)
        cat > "$RULE" <<EOF
// Steam Frame Helper: Wi-Fi scan without a password prompt in RDP (xrdp) sessions.
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.NetworkManager.wifi.scan" &&
        subject.user == "$TARGET_USER") {
        return polkit.Result.YES;
    }
});
EOF
        chmod 644 "$RULE"
        ;;
    remove)
        rm -f "$RULE"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
