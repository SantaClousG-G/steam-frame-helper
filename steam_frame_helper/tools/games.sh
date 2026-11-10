#!/bin/bash
# Steam games maintenance: save backups, shader cache, Proton prefixes.
# Usage:
#   games.sh list                     -> TSV: appid name kind(proton|android|native) shader_size backups
#   games.sh backup <appid>           -> creates backup, prints its path
#   games.sh backups <appid>          -> lists backup files, newest first
#   games.sh restore <appid> <file>
#   games.sh clear-shaders <appid>
#   games.sh reset-prefix <appid>     -> backs up saves first, then deletes prefix
# Runs as the user, no root needed.

set -u

STEAM="$HOME/.local/share/Steam"
APPS="$STEAM/steamapps"
BACKUPS="$HOME/steam_frame_helper_backups"
TOOLS="$(cd "$(dirname "$0")" && pwd)"
. "$TOOLS/i18n.sh"

acf_value() {
    # acf_value <file> <key>
    awk -v k="\"$2\"" '$1 == k { v = $0; sub(/^[^"]*"[^"]*"[ \t]*"/, "", v); sub(/"[ \t]*$/, "", v); print v; exit }' "$1"
}

check_appid() {
    case "$1" in
        '' | *[!0-9]*) echo "Bad appid: $1" >&2; exit 2 ;;
    esac
}

# Relative to $HOME, so archives restore in place.
save_paths() {
    local id="$1" p data="${APPS#$HOME/}/compatdata/$id"
    # Windows game (Proton prefix).
    p="$data/pfx/drive_c/users/steamuser"
    [ -d "$HOME/$p" ] && echo "$p"
    # Android game (APK container): app data and shared storage.
    for p in "$data/internal" "$data/external"; do
        [ -d "$HOME/$p" ] && echo "$p"
    done
    for p in "$STEAM"/userdata/*/"$id"; do
        [ -d "$p" ] && echo "${p#$HOME/}"
    done
}

list_games() {
    local m id name dir kind shader count
    for m in "$APPS"/appmanifest_*.acf; do
        [ -f "$m" ] || continue
        id="$(acf_value "$m" appid)"
        name="$(acf_value "$m" name)"
        dir="$(acf_value "$m" installdir)"
        # Proton, Steam Linux Runtime and other tools ship a toolmanifest.
        [ -f "$APPS/common/$dir/toolmanifest.vdf" ] && continue
        kind=native
        if [ -d "$APPS/compatdata/$id/pfx" ]; then
            kind=proton
        elif [ -d "$APPS/compatdata/$id/internal" ]; then
            kind=android
        fi
        shader="-"
        [ -d "$APPS/shadercache/$id" ] && shader="$(du -sh "$APPS/shadercache/$id" | cut -f1)"
        count=0
        [ -d "$BACKUPS/$id" ] && count="$(find "$BACKUPS/$id" -name '*.tar.gz' | wc -l)"
        printf '%s\t%s\t%s\t%s\t%s\n' "$id" "$name" "$kind" "$shader" "$count"
    done
}

backup() {
    local id="$1" paths file
    mapfile -t paths < <(save_paths "$id")
    if [ "${#paths[@]}" -eq 0 ]; then
        echo "$(t "Нет сохранений для $id" "No saves found for $id")" >&2
        exit 3
    fi
    mkdir -p "$BACKUPS/$id"
    file="$BACKUPS/$id/$(date +%Y%m%d-%H%M%S).tar.gz"
    tar -czf "$file" -C "$HOME" \
        --exclude='*/AppData/Local/Temp' \
        --exclude='*/AppData/Local/Microsoft' \
        --exclude='*/internal/*/cache' \
        "${paths[@]}"
    echo "$file"
}

case "${1:-list}" in
    list)
        list_games
        ;;
    backup)
        check_appid "${2:-}"
        backup "$2"
        ;;
    backups)
        check_appid "${2:-}"
        [ -d "$BACKUPS/$2" ] && ls -1t "$BACKUPS/$2"/*.tar.gz 2>/dev/null
        exit 0
        ;;
    restore)
        check_appid "${2:-}"
        case "${3:-}" in
            "$BACKUPS/$2/"*.tar.gz) ;;
            *) echo "Bad backup file: ${3:-}" >&2; exit 2 ;;
        esac
        tar -xzf "$3" -C "$HOME"
        ;;
    clear-shaders)
        check_appid "${2:-}"
        rm -rf "${APPS:?}/shadercache/$2"
        ;;
    reset-prefix)
        check_appid "${2:-}"
        if [ -n "$(save_paths "$2")" ]; then
            backup "$2"
        fi
        rm -rf "${APPS:?}/compatdata/$2"
        ;;
    *)
        echo "Usage: see header of $0" >&2
        exit 1
        ;;
esac
