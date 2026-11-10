#!/bin/bash
# Decky Loader for Steam Frame (official ARM64 build).
# Mirrors SteamDeckHomebrew/decky-installer cli/install_release.sh,
# plus SHA-256 verification against the GitHub release digest.
# Usage: decky.sh status | install | repair | remove
# All commands require root (settings and service files are root-owned).

set -u

# Third-party plugin store (Decky "Custom" store channel).
STORE_URL=https://repo.steamdeckbase.org/decky/plugins
STORE_CUSTOM=2

RELEASES_API=https://api.github.com/repos/SteamDeckHomebrew/decky-loader/releases
RELEASES_WEB=https://github.com/SteamDeckHomebrew/decky-loader/releases
SERVICE_URL=https://raw.githubusercontent.com/SteamDeckHomebrew/decky-loader/main/dist/plugin_loader-release.service
SYSTEM_SERVICE=/etc/systemd/system/plugin_loader.service
TOOLS="$(cd "$(dirname "$0")" && pwd)"

TARGET_USER="${SUDO_USER:-${PKEXEC_UID:+$(id -nu "$PKEXEC_UID")}}"
TARGET_USER="${TARGET_USER:-$(id -nu)}"
USER_DIR="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
HOMEBREW="$USER_DIR/homebrew"
SERVICES="$HOMEBREW/services"
CEF_FLAG="$USER_DIR/.steam/steam/.cef-enable-remote-debugging"
SETTINGS="$HOMEBREW/settings/loader.json"

as_user() {
    if [ "$(id -u)" -eq 0 ] && [ "$TARGET_USER" != root ]; then
        sudo -u "$TARGET_USER" "$@"
    else
        "$@"
    fi
}

asset_name() {
    case "$(uname -m)" in
        aarch64 | arm64) echo PluginLoader-arm64 ;;
        *) echo PluginLoader ;;
    esac
}

# Prints: version<TAB>url<TAB>sha256 of the latest stable release asset.
latest_release() {
    latest_release_api || latest_release_web
}

latest_release_api() {
    local json
    json="$(curl -fsSL "$RELEASES_API" 2>/dev/null)" || return 1
    python3 -c '
import json, sys
asset = sys.argv[1]
for rel in json.loads(sys.argv[2]):
    if rel.get("prerelease") or rel.get("draft"):
        continue
    for a in rel.get("assets", []):
        if a["name"] == asset:
            digest = (a.get("digest") or "").removeprefix("sha256:")
            print(rel["tag_name"], a["browser_download_url"], digest, sep="\t")
            sys.exit(0)
sys.exit(1)
' "$(asset_name)" "$json"
}

# Fallback when the GitHub API is rate-limited: the latest tag comes from the
# releases/latest redirect, the digest from the release assets page, where
# GitHub prints "sha256:<hex>" right after each asset link.
latest_release_web() {
    local tag asset url page sha
    tag="$(curl -fsSI "$RELEASES_WEB/latest" | awk 'tolower($1) == "location:" { n = split($2, p, "/"); print p[n] }' | tr -d '\r')"
    [ -n "$tag" ] || return 1
    asset="$(asset_name)"
    url="$RELEASES_WEB/download/$tag/$asset"
    page="$(curl -fsSL "$RELEASES_WEB/expanded_assets/$tag")" || return 1
    sha="$(python3 -c '
import sys
link, page = sys.argv[1], sys.argv[2]
start = page.find(link + "\"")
if start < 0:
    sys.exit(1)
pos = page.find("sha256:", start)
digest = page[pos + 7:pos + 71] if pos >= 0 else ""
if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
    sys.exit(1)
print(digest)
' "${url#https://github.com}" "$page")" || return 1
    printf '%s\t%s\t%s\n' "$tag" "$url" "$sha"
}

do_status() {
    local version="" active port
    [ -f "$SERVICES/.loader.version" ] && version="$(cat "$SERVICES/.loader.version")"
    active="$(systemctl is-active plugin_loader 2>/dev/null)"
    port="нет"
    ss -ltn 2>/dev/null | grep -q ':1337 ' && port="да"
    if [ -f "$SYSTEM_SERVICE" ] && [ -x "$SERVICES/PluginLoader" ]; then
        echo "installed=1"
        echo "info=Decky ${version:-?}  ·  служба: ${active:-?}  ·  порт 1337: $port  ·  магазин: $(store_name)  ·  плагинов: $(find "$HOMEBREW/plugins" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
    else
        echo "installed=0"
        echo "info=Не установлен (официальная сборка $(asset_name))"
    fi
}

do_install() {
    local info version url sha
    tmp=""
    info="$(latest_release)" || { echo "Не удалось получить релиз Decky с GitHub" >&2; exit 1; }
    IFS=$'\t' read -r version url sha <<< "$info"
    if [ -z "$sha" ]; then
        echo "У релиза $version нет SHA-256, установка отменена" >&2
        exit 1
    fi

    tmp="$(mktemp)"
    trap 'rm -f "${tmp:-}"' EXIT
    curl -fL --retry 2 -o "$tmp" "$url" || { echo "Ошибка загрузки $url" >&2; exit 1; }
    if [ "$(sha256sum "$tmp" | cut -d' ' -f1)" != "$sha" ]; then
        echo "SHA-256 не совпал, установка отменена" >&2
        exit 1
    fi

    prepare_dirs
    systemctl stop plugin_loader 2>/dev/null
    install -m 755 -o "$TARGET_USER" "$tmp" "$SERVICES/PluginLoader"
    echo "$version" > "$SERVICES/.loader.version"

    write_service
    set_store
    install_bundled_plugins
    systemctl daemon-reload
    systemctl enable --now plugin_loader
    shortcut add
    echo "Decky $version установлен"
}

# Plugins shipped with Steam Frame Helper (decky-plugin/<folder>), e.g.
# SFH-Frame-Menu that adds "Decky" to the Frame left menu. Permissions mirror
# decky_loader/browser.py: files owned by the user, folder and plugin.json by root.
install_bundled_plugins() {
    local src dst
    for src in "$(dirname "$TOOLS")"/decky-plugin/*/; do
        [ -f "$src/plugin.json" ] || continue
        dst="$HOMEBREW/plugins/$(basename "$src")"
        rm -rf "$dst"
        cp -r "$src" "$dst"
        chown -R "$TARGET_USER:" "$dst"
        chown root: "$dst" "$dst/plugin.json"
        chmod 755 "$dst" "$dst/plugin.json"
    done
}

prepare_dirs() {
    mkdir -p "$HOMEBREW/plugins" "$HOMEBREW/settings" "$SERVICES/.systemd"
    # plugins/ stays root-owned: Decky chowns it to its effective user on start.
    chown "$TARGET_USER:" "$HOMEBREW" "$HOMEBREW/settings" "$SERVICES" "$SERVICES/.systemd"
    as_user touch "$CEF_FLAG"
}

write_service() {
    if curl -fsSL "$SERVICE_URL" -o "$SERVICES/.systemd/plugin_loader-release.service"; then
        sed -e "s|\${HOMEBREW_FOLDER}|$HOMEBREW|g" \
            "$SERVICES/.systemd/plugin_loader-release.service" > "$SYSTEM_SERVICE"
    else
        cat > "$SYSTEM_SERVICE" <<EOF
[Unit]
Description=SteamDeck Plugin Loader
After=network.target
[Service]
Type=simple
User=root
Restart=always
ExecStart=$SERVICES/PluginLoader
WorkingDirectory=$SERVICES
Environment=UNPRIVILEGED_PATH=$HOMEBREW
Environment=PRIVILEGED_PATH=$HOMEBREW
Environment=LOG_LEVEL=INFO
[Install]
WantedBy=multi-user.target
EOF
    fi
}

# Decky reads settings at start, so the service must be stopped while editing.
set_store() {
    python3 - "$SETTINGS" "$STORE_URL" "$STORE_CUSTOM" <<'PY'
import json, os, sys
path, url, channel = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    with open(path) as f:
        data = json.load(f)
except (OSError, ValueError):
    data = {}
data["store"] = channel
data["store-url"] = url
data["store_select.warn.third_party"] = True
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(data, f, indent=4)
os.replace(tmp, path)
PY
}

store_name() {
    python3 - "$SETTINGS" "$STORE_URL" "$STORE_CUSTOM" <<'PY'
import json, sys
path, url, channel = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    with open(path) as f:
        data = json.load(f)
except (OSError, ValueError):
    data = {}
if data.get("store") == channel and data.get("store-url") == url:
    print("steamdeckbase")
elif data.get("store") == channel:
    print("свой: " + str(data.get("store-url")))
else:
    print({0: "официальный", 1: "testing"}.get(data.get("store", 0), "?"))
PY
}

do_repair() {
    if [ ! -x "$SERVICES/PluginLoader" ]; then
        echo "Бинарник Decky не найден — переустановка"
        do_install
        return
    fi
    systemctl stop plugin_loader 2>/dev/null
    prepare_dirs
    [ -f "$SYSTEM_SERVICE" ] || write_service
    set_store
    install_bundled_plugins
    systemctl daemon-reload
    systemctl enable plugin_loader
    systemctl restart plugin_loader
    shortcut add
    echo "Decky починен: служба, права, магазин, ярлык"
}

# "Decky" entry in the Steam library: Frame has no Quick Access Menu in VR.
shortcut() {
    as_user env XDG_RUNTIME_DIR="/run/user/$(id -u "$TARGET_USER")" \
        python3 "$TOOLS/steam_shortcut.py" "$1"
}

do_remove() {
    # Plugins in ~/homebrew/plugins are kept.
    shortcut remove
    systemctl disable --now plugin_loader 2>/dev/null
    rm -f "$SYSTEM_SERVICE" "$USER_DIR/.config/systemd/user/plugin_loader.service"
    systemctl daemon-reload
    rm -f "$SERVICES/PluginLoader" "$SERVICES/.loader.version"
}

case "${1:-status}" in
    status) do_status ;;
    install) do_install ;;
    repair) do_repair ;;
    remove) do_remove ;;
    *)
        echo "Usage: $0 status | install | repair | remove" >&2
        exit 1
        ;;
esac
