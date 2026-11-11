#!/bin/bash
# sudo without a password for the user (SFH, SSH scripts, Konsole).
# The rule is a separate file in /etc/sudoers.d, checked with visudo before it is put in
# place; removing it restores the password prompt. "zz-" makes it the last file read,
# so it wins over the stock rules (in sudoers the last matching rule applies).
# Usage: sudo_nopasswd.sh status | install | remove      (install/remove: root)

set -u

TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

RULE=/etc/sudoers.d/zz-sfh-nopasswd
TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}}"
TARGET_USER="${TARGET_USER:-$(id -nu)}"

case "${1:-status}" in
    status)
        # run as the user: the rule file itself is not readable without root
        if sudo -n true 2>/dev/null; then
            echo "installed=1"
            echo "info=$(t "sudo работает без пароля (можно выключить: пароль снова будет спрашиваться)" "sudo works without a password (turn off to require the password again)")"
        else
            echo "installed=0"
            echo "info=$(t "sudo спрашивает пароль. Включите, чтобы SFH и команды в Konsole не спрашивали его каждый раз" "sudo asks for the password. Turn on so SFH and Konsole commands don't ask every time")"
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
        ;;
    remove)
        rm -f "$RULE"
        ;;
    *)
        echo "Usage: $0 status | install | remove" >&2
        exit 1
        ;;
esac
