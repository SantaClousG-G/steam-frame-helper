"""UI language for Steam Frame Helper and its Python tools.

Russian strings are the source text in the code; English comes from i18n_en.EN, keyed by
the exact Russian string. Strings with placeholders are translated before formatting:
    _("Установлено: {n}").format(n=3)

Language: SFH_LANG (ru|en; set by the app for every tool it runs) → the choice saved in
ui_state.json ("language") → the Steam client language → the system locale (ru* → ru) → en.
"""

import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
UI_STATE = os.path.join(APP_DIR, "ui_state.json")
LANGUAGES = (("ru", "Русский"), ("en", "English"))


def user_home():
    """Home of the desktop user, also when running as root through sudo / pkexec."""
    try:
        import pwd
        if os.environ.get("SUDO_USER"):
            return pwd.getpwnam(os.environ["SUDO_USER"]).pw_dir
        if os.environ.get("PKEXEC_UID"):
            return pwd.getpwuid(int(os.environ["PKEXEC_UID"])).pw_dir
    except (ImportError, KeyError, ValueError):
        pass
    return os.path.expanduser("~")


def steam_language():
    """Steam client language from registry.vdf ("language" "russian"), or ""."""
    try:
        with open(os.path.join(user_home(), ".steam", "registry.vdf"),
                  encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split('"')
                # ['\t\t', 'language', '\t\t', 'russian', '\n']
                if len(parts) >= 4 and parts[1].lower() == "language":
                    return parts[3].lower()
    except OSError:
        pass
    return ""


def detect_language():
    env = os.environ.get("SFH_LANG", "")
    if env in ("ru", "en"):
        return env
    try:
        with open(UI_STATE, encoding="utf-8") as f:
            saved = json.load(f).get("language")
        if saved in ("ru", "en"):
            return saved
    except (OSError, ValueError, AttributeError):
        pass
    # SteamOS sets the system locale to en_US even when Steam itself is in Russian,
    # so the Steam client language comes before the locale.
    steam = steam_language()
    if steam:
        return "ru" if steam == "russian" else "en"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "ru" if value.lower().startswith("ru") else "en"
    return "en"


LANG = detect_language()
os.environ["SFH_LANG"] = LANG      # tools started by the app inherit the language

if LANG == "en":
    try:
        from i18n_en import EN
    except ImportError:
        EN = {}
else:
    EN = {}


def _(text):
    """Translated text (Russian source string → English when the UI is English)."""
    return EN.get(text, text) if EN else text


def T(ru, en):
    """Inline pair for tools with few strings: T("Готово", "Done")."""
    return en if LANG == "en" else ru
