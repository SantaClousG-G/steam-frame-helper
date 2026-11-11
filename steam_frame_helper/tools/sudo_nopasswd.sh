#!/bin/bash
# Administrator rights without a password for the user: sudo (SFH, SSH scripts, Konsole)
# and polkit (system password dialogs, e.g. the network widget in the headset desktop or
# RDP, pkexec). With passwordless sudo the user can become root anyway, so the polkit
# rule adds no new rights, only removes the dialogs.
#
# sudo: /etc/sudoers.d/zz-sfh-nopasswd, checked with visudo before it is put in place;
#       "zz-" makes it the last file read, so it wins (in sudoers the last match applies).
# polkit: /etc/polkit-1/rules.d/49-sfh-nopasswd.rules, read before the stock 50-* rules.
# Removing both files restores the password prompts.
# Usage: sudo_nopasswd.sh status | install | remove      (install/remove: root)

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

RULE=/etc/sudoers.d/zz-sfh-nopasswd
POLKIT_RULE=/etc/polkit-1/rules.d/49-sfh-nopasswd.rules
# rules.d is not readable by the user: a world-readable marker lets `status` run without root
MARKER=/etc/sfh/admin-nopasswd
TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}}"
TARGET_USER="${TARGET_USER:-$(id -nu)}"

case "${1:-status}" in
    status)
        # run as the user: the rule files themselves are not readable without root
        if sudo -n true 2>/dev/null && [ -f "$MARKER" ]; then
            echo "installed=1"
            echo "info=$(t "sudo и системные окна не спрашивают пароль (выключите, чтобы пароль снова спрашивался)" "sudo and system dialogs don't ask for the password (turn off to require it again)")"
        else
            echo "installed=0"
            echo "info=$(t "sudo и системные окна спрашивают пароль. Включите, чтобы SFH, Konsole и рабочий стол не спрашивали его каждый раз" "sudo and system dialogs ask for the password. Turn on so SFH, Konsole and the desktop don't ask every time")"
        fi
        ;;
    install)
        if [ "$TARGET_USER" = "root" ]; then
            echo "$(t "Не удалось определить пользователя" "Could not determine the user")" >&2
            exit 1
        fi
        tmp="$(mktemp)"
        trap 'rm -f "$tmp"' EXIT
        echo "# Steam Frame Helper: sudo without a password for $TARGET_USER" > "$tmp"
        echo "$TARGET_USER ALL=(ALL) NOPASSWD: ALL" >> "$tmp"
        if ! visudo -cqf "$tmp"; then
            echo "$(t "Правило не прошло проверку visudo, ничего не изменено" "The rule failed the visudo check, nothing changed")" >&2
            exit 1
        fi
        install -m 440 -o root -g root "$tmp" "$RULE"
        cat > "$POLKIT_RULE" <<EOF
// Steam Frame Helper: no password dialogs for $TARGET_USER (sudo is passwordless too).
polkit.addRule(function(action, subject) {
    if (subject.user == "$TARGET_USER") {
        return polkit.Result.YES;
    }
});
EOF
        chmod 644 "$POLKIT_RULE"
        mkdir -p /etc/sfh && : > "$MARKER" && chmod 644 "$MARKER"
        ;;
    remove)
        rm -f "$RULE" "$POLKIT_RULE" "$MARKER"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
