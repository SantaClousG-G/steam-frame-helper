#!/bin/bash
# Steam Frame Helper installer.
#
#   curl -fsSL https://raw.githubusercontent.com/SantaClousG-G/steam-frame-helper/main/install.sh | bash
#
# Installs (or updates) the app into ~/.config/steam_frame_helper and adds
# "Steam Frame Helper" to the application menu. Files that exist only locally
# (settings, tokens, scripts added by hand) are kept on update.
#
# Options (environment variables):
#   SFH_VERSION=v1.0.0   install this release instead of the latest
#   SFH_ARCHIVE=path     install from a local release archive (no download)
#   bash install.sh --uninstall   remove the app and its menu entry
#                                 (system tweaks made from the app stay as they are)

set -euo pipefail

REPO="SantaClousG-G/steam-frame-helper"
ASSET="steam-frame-helper.tar.gz"
APP_DIR="$HOME/.config/steam_frame_helper"
DESKTOP_FILE="$HOME/.local/share/applications/steam_frame_helper.desktop"

# messages follow the system language (Russian for ru*, English otherwise)
case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in ru*|RU*) SFH_LANG=ru ;; *) SFH_LANG=en ;; esac
t() { if [ "$SFH_LANG" = "en" ]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }
say() { printf '\033[1;36m>>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m%s:\033[0m %s\n' "$(t "Ошибка" "Error")" "$*" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now sfh-vr-hud.service sfh-screenshots.service >/dev/null 2>&1 || true
    rm -f "$HOME/.config/systemd/user/sfh-vr-hud.service" "$HOME/.config/systemd/user/sfh-screenshots.service"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    rm -rf "$APP_DIR"
    rm -f "$DESKTOP_FILE"
    say "$(t "Steam Frame Helper удалён. Твики системы (регион, Decky и т.п.) остались как были." "Steam Frame Helper removed. System tweaks (region, Decky, etc.) stay as they are.")"
    exit 0
fi

[ "$(id -u)" -ne 0 ] || die "$(t "запускай от обычного пользователя, не через sudo" "run as a regular user, not with sudo")"
if [ "$(uname -m)" != "aarch64" ]; then
    say "$(t "Внимание: это не Steam Frame (архитектура $(uname -m)). Часть функций работать не будет." "Warning: this is not a Steam Frame (architecture $(uname -m)). Some features will not work.")"
fi
command -v python3 >/dev/null || die "$(t "нужен python3" "python3 is required")"
python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' 2>/dev/null \
    || die "$(t "нужен GTK3 для Python (python-gobject) — на SteamOS он есть из коробки" "GTK3 for Python (python-gobject) is required — SteamOS ships with it")"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [ -n "${SFH_ARCHIVE:-}" ]; then
    cp "$SFH_ARCHIVE" "$TMP/$ASSET"
else
    if [ -n "${SFH_VERSION:-}" ]; then
        URL="https://github.com/$REPO/releases/download/$SFH_VERSION/$ASSET"
    else
        URL="https://github.com/$REPO/releases/latest/download/$ASSET"
    fi
    say "$(t "Скачиваю" "Downloading") $URL"
    curl -fL --progress-bar "$URL" -o "$TMP/$ASSET" || die "$(t "не удалось скачать релиз" "could not download the release")"
fi

tar -xzf "$TMP/$ASSET" -C "$TMP"
[ -f "$TMP/steam_frame_helper/steam_frame_helper.py" ] || die "$(t "в архиве нет steam_frame_helper/" "steam_frame_helper/ is missing from the archive")"

say "$(t "Устанавливаю в" "Installing to") $APP_DIR"
mkdir -p "$APP_DIR"
# copy over the existing install without deleting local-only files
cp -a "$TMP/steam_frame_helper/." "$APP_DIR/"
chmod +x "$APP_DIR"/tools/*.sh "$APP_DIR"/tools/*.py "$APP_DIR/steam_frame_helper.py"

mkdir -p "$(dirname "$DESKTOP_FILE")"
sed "s|@APP_DIR@|$APP_DIR|g" "$APP_DIR/steam_frame_helper.desktop" > "$DESKTOP_FILE"
update-desktop-database "$(dirname "$DESKTOP_FILE")" >/dev/null 2>&1 || true

# services that run from the app folder pick up the new files
for unit in sfh-vr-hud.service sfh-screenshots.service; do
    if systemctl --user is-active --quiet "$unit" 2>/dev/null; then
        systemctl --user restart "$unit" || true
    fi
done

VERSION="$(cat "$APP_DIR/VERSION" 2>/dev/null || echo "?")"
say "$(t "Готово" "Done"): Steam Frame Helper $VERSION"
say "$(t "Запуск: меню приложений → Steam Frame Helper (режим рабочего стола)" "Start: application menu → Steam Frame Helper (Desktop Mode)")"
say "$(t "        или" "        or"): python3 $APP_DIR/steam_frame_helper.py"
