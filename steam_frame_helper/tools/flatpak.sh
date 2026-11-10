#!/bin/bash
# Flatpak apps from Flathub (system installation).
# Usage:
#   flatpak.sh list            -> TSV: application name version
#   flatpak.sh search <query>  -> TSV: application name description
#   flatpak.sh install <id>    (root)
#   flatpak.sh remove <id>     (root)
#   flatpak.sh fix-flathub     (root)

set -u

FLATHUB_REPO=https://dl.flathub.org/repo/flathub.flatpakrepo
FLATHUB_URL=https://dl.flathub.org/repo/
FLATHUB_KEY=https://dl.flathub.org/repo/flathub.gpg

check_id() {
    case "$1" in
        '' | *[!A-Za-z0-9._-]*) echo "Bad application id: $1" >&2; exit 2 ;;
    esac
}

case "${1:-list}" in
    list)
        flatpak list --app --system --columns=application,name,version
        ;;
    search)
        flatpak search --columns=application,name,description -- "${2:-}" \
            | grep -v '^No matches found'
        exit 0
        ;;
    install)
        check_id "${2:-}"
        flatpak install -y --noninteractive --system flathub "$2"
        ;;
    remove)
        check_id "${2:-}"
        flatpak uninstall -y --noninteractive --system "$2"
        ;;
    fix-flathub)
        flatpak remote-add --if-not-exists --system flathub "$FLATHUB_REPO"
        flatpak remote-modify --system --url="$FLATHUB_URL" flathub
        key="$(mktemp)"
        trap 'rm -f "$key"' EXIT
        curl -fsSL "$FLATHUB_KEY" -o "$key"
        flatpak remote-modify --system --gpg-import="$key" flathub
        flatpak update -y --noninteractive --appstream --system
        ;;
    *)
        echo "Usage: see header of $0" >&2
        exit 1
        ;;
esac
