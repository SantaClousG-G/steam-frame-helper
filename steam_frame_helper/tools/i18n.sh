#!/bin/bash
# UI language for the shell tools of Steam Frame Helper. Source it:
#   . "$(dirname "$0")/i18n.sh"
#   echo "info=$(t "Включено" "Enabled")"
# Language: SFH_LANG (ru|en; the app sets it for every tool it runs) → otherwise the
# same detection as i18n.py (saved choice → Steam client language → system locale).

if [ "${SFH_LANG:-}" != "ru" ] && [ "${SFH_LANG:-}" != "en" ]; then
    _sfh_app="$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")")"
    SFH_LANG="$(SFH_LANG= python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
import i18n
print(i18n.LANG)
' "$_sfh_app" 2>/dev/null)"
    [ "$SFH_LANG" = "ru" ] || SFH_LANG=en
    export SFH_LANG
fi

# t "<russian>" "<english>"  → the text for the current language (no trailing newline)
t() {
    if [ "$SFH_LANG" = "en" ]; then printf '%s' "$2"; else printf '%s' "$1"; fi
}
