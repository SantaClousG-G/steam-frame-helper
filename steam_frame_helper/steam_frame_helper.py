#!/usr/bin/env python3
"""Steam Frame Helper: GTK3 utility with system tweaks for Steam Frame."""

import json
import os
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402
from i18n import LANG, LANGUAGES, T, _  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(APP_DIR, "tools")
try:
    with open(os.path.join(APP_DIR, "VERSION"), encoding="utf-8") as _f:
        VERSION = _f.read().strip()
except OSError:
    VERSION = "dev"

REGIONS = [
    ("DE", _("Германия")),
    ("PL", _("Польша")),
    ("FI", _("Финляндия")),
    ("NL", _("Нидерланды")),
    ("FR", _("Франция")),
    ("GB", _("Великобритания")),
    ("US", _("США")),
    ("RU", _("Россия")),
]

CSS = b"""
window { background-color: #1b1e24; color: #e6e6e6; }
.tool-row { background-color: #242830; border-radius: 8px; padding: 12px; margin: 6px 12px; }
.section { font-size: 13px; font-weight: bold; color: #8b949e; margin: 14px 16px 2px 16px; }
expander.section-exp > title { padding: 12px 16px 2px 12px; }
expander.section-exp > title > arrow { color: #8b949e; min-width: 16px; min-height: 16px; }
.section-title { font-size: 13px; font-weight: bold; color: #8b949e; margin-left: 4px; }
.tool-title { font-size: 15px; font-weight: bold; }
.tool-sub { color: #8b949e; }
.status-ok { color: #3fb950; font-size: 26px; font-weight: bold; }
.status-no { color: #f85149; font-size: 26px; font-weight: bold; }
.danger { color: #f85149; }
.log { font-family: monospace; color: #8b949e; padding: 6px 16px; }
"""


# ---------- process helpers ----------

def tool(name):
    return os.path.join(TOOLS_DIR, name)


def user_session_env():
    """Environment for tools that talk to the user's systemd and Steam.

    In the desktop shown inside the headset SFH runs in a nested Plasma session with
    XDG_RUNTIME_DIR=/run/user/<uid>/nested_plasma and its own D-Bus; `systemctl --user`
    looks for the user manager there and fails ("could not enable the service"). Point
    child tools at the real session; GUI launches (xdg-open) keep the nested one."""
    env = dict(os.environ)
    real = f"/run/user/{os.getuid()}"
    if env.get("XDG_RUNTIME_DIR") != real and os.path.exists(f"{real}/systemd/private"):
        env["XDG_RUNTIME_DIR"] = real
        if os.path.exists(f"{real}/bus"):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={real}/bus"
    return env


def run_user(args):
    return subprocess.run(args, capture_output=True, text=True, env=user_session_env())


# One password dialog at a time: parallel pkexec calls make polkit cancel some of them.
PKEXEC_LOCK = threading.Lock()


def run_root(args, ask_password=True):
    """Run as root: passwordless sudo first, pkexec as fallback.

    ask_password=False never opens a password dialog: without passwordless sudo the
    command runs as the user (status checks are written to work that way)."""
    # sudo and pkexec drop the environment: pass the UI language explicitly
    lang = ["env", f"SFH_LANG={LANG}"]
    try:
        res = subprocess.run(["sudo", "-n"] + lang + args, capture_output=True, text=True)
        if not (res.returncode != 0 and "password" in res.stderr):
            return res
    except FileNotFoundError:
        pass
    if not ask_password:
        return run_user(args)
    try:
        with PKEXEC_LOCK:
            return subprocess.run(["pkexec"] + lang + args, capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 1, "", _("Нет прав root (sudo/pkexec)"))


def run_status_root(args):
    return run_root(args, ask_password=False)


def parse_kv(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def parse_tsv(text, columns):
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= columns:
            rows.append(parts[:columns])
    return rows


def error_text(res):
    text = (res.stderr or res.stdout or "").strip()
    return text.splitlines()[-1] if text else _("код {code}").format(code=res.returncode)


class Runner:
    """Runs commands in a thread and reports to the status line."""

    def __init__(self, log):
        self.log = log

    def run(self, func, args, message, on_done=None, widgets=()):
        for w in widgets:
            w.set_sensitive(False)
        self.log(message + "…")

        def worker():
            res = func(args)
            GLib.idle_add(done, res)

        def done(res):
            if res.returncode == 0:
                self.log(_("{message} — готово").format(message=message))
            else:
                self.log(_("{message} — ошибка: {error}").format(message=message,
                                                          error=error_text(res)))
            for w in widgets:
                w.set_sensitive(True)
            if on_done:
                on_done(res)
            return False

        threading.Thread(target=worker, daemon=True).start()


def confirm(parent, text, secondary=""):
    dlg = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.OK_CANCEL,
        text=text,
    )
    if secondary:
        dlg.format_secondary_text(secondary)
    ok = dlg.run() == Gtk.ResponseType.OK
    dlg.destroy()
    return ok


# ---------- widgets ----------

def row_box():
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    box.get_style_context().add_class("tool-row")
    return box


def full_text_tooltip(label):
    """Ellipsized labels show their whole text as a tooltip, kept in sync on updates."""
    label.set_tooltip_text(label.get_text())
    label.connect("notify::label", lambda lbl, _p: lbl.set_tooltip_text(lbl.get_text()))


def title_block(title):
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    t = Gtk.Label(label=title, xalign=0)
    t.get_style_context().add_class("tool-title")
    t.set_ellipsize(Pango.EllipsizeMode.END)
    full_text_tooltip(t)
    sub = Gtk.Label(label="…", xalign=0)
    sub.set_ellipsize(Pango.EllipsizeMode.END)
    sub.get_style_context().add_class("tool-sub")
    full_text_tooltip(sub)
    text.pack_start(t, False, False, 0)
    text.pack_start(sub, False, False, 0)
    return text, sub


def section(title):
    lbl = Gtk.Label(label=title.upper(), xalign=0)
    lbl.get_style_context().add_class("section")
    return lbl


UI_STATE = os.path.join(APP_DIR, "ui_state.json")


def load_ui_state():
    try:
        with open(UI_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_ui_state(key, value):
    state = load_ui_state()
    state[key] = value
    try:
        with open(UI_STATE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(UI_STATE + ".tmp", UI_STATE)
    except OSError:
        pass


class Section(Gtk.Expander):
    """Collapsible group of rows with a section-style title. The expanded/collapsed
    state is remembered per key in ui_state.json."""

    def __init__(self, key, title):
        super().__init__()
        self.key = key
        lbl = Gtk.Label(label=title.upper(), xalign=0)
        lbl.get_style_context().add_class("section-title")
        self.set_label_widget(lbl)
        self.get_style_context().add_class("section-exp")
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.body)
        self.set_expanded(load_ui_state().get(f"section.{key}", True))
        self.connect("notify::expanded",
                     lambda exp, _p: save_ui_state(f"section.{key}", exp.get_expanded()))

    def add_row(self, widget):
        self.body.pack_start(widget, False, False, 0)
        return widget


def page():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.set_margin_bottom(12)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.add(box)
    return scroll, box


class StatusTool(Gtk.Box):
    """Tool row with ✔/✖ status and install/remove buttons.

    The script answers `status` with installed=0|1 and info=<text>,
    and `install` / `remove` change the state (run as root).
    """

    def __init__(self, runner, title, script, install_label=_("Установить"),
                 remove_label=_("Удалить"), status_as_root=False, reinstall=False,
                 repair=False, actions_as_root=True):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.runner = runner
        self.script = tool(script)
        self.title = title
        self.status_as_root = status_as_root
        self.reinstall = reinstall
        self.repair = repair
        self.actions_as_root = actions_as_root
        self.get_style_context().add_class("tool-row")

        self.mark = Gtk.Label()
        self.mark.set_size_request(36, -1)
        self.pack_start(self.mark, False, False, 0)

        text, self.sub = title_block(title)
        self.pack_start(text, True, True, 0)

        self.extra = self.build_extra()
        if self.extra is not None:
            self.pack_start(self.extra, False, False, 0)

        self.btn_install = Gtk.Button(label=install_label)
        self.btn_install.connect("clicked", lambda _b: self.act("install", install_label))
        self.pack_start(self.btn_install, False, False, 0)

        self.btn_repair = None
        if self.repair:
            self.btn_repair = Gtk.Button(label=_("Починить"))
            self.btn_repair.connect("clicked", lambda _b: self.act("repair", _("Починить")))
            self.pack_start(self.btn_repair, False, False, 0)

        self.btn_remove = Gtk.Button(label=remove_label)
        self.btn_remove.connect("clicked", lambda _b: self.act("remove", remove_label))
        self.pack_start(self.btn_remove, False, False, 0)

        self.refresh()

    def build_extra(self):
        return None

    def install_args(self):
        return []

    def on_status(self, info):
        pass

    def widgets(self):
        return [w for w in (self.btn_install, self.btn_repair, self.btn_remove, self.extra) if w]

    def refresh(self):
        def done(res):
            info = parse_kv(res.stdout)
            installed = info.get("installed") == "1"
            ctx = self.mark.get_style_context()
            ctx.remove_class("status-ok")
            ctx.remove_class("status-no")
            self.mark.set_text("✔" if installed else "✖")
            ctx.add_class("status-ok" if installed else "status-no")
            self.sub.set_text(info.get("info", error_text(res)))
            self.btn_install.set_sensitive(
                not installed or self.extra is not None or self.reinstall)
            self.btn_remove.set_sensitive(installed)
            if self.btn_repair:
                self.btn_repair.set_sensitive(installed)
            self.on_status(info)
            return False

        func = run_status_root if self.status_as_root else run_user
        threading.Thread(
            target=lambda: GLib.idle_add(done, func([self.script, "status"])),
            daemon=True,
        ).start()

    def act(self, cmd, label):
        args = [self.script, cmd] + (self.install_args() if cmd == "install" else [])
        func = run_root if self.actions_as_root else run_user
        self.runner.run(func, args, f"{self.title}: {label}",
                        on_done=lambda _r: self.refresh(), widgets=self.widgets())


class VrHudTool(StatusTool):
    """Connection stats overlay in the headset (tools/vr_hud.py): install = autostart
    service; the extra button shows/hides it."""

    def __init__(self, runner):
        super().__init__(runner, _("Статистика соединения с ПК (в шлеме)"), "vr_hud.sh",
                         install_label=_("Включить"), remove_label=_("Выключить"),
                         actions_as_root=False)

    def build_extra(self):
        btn = Gtk.Button(label=_("Показать / скрыть"))
        btn.connect("clicked", lambda _b: self.runner.run(
            run_user, [self.script, "toggle"], f"{self.title}: {_('показать / скрыть')}",
            widgets=self.widgets()))
        return btn

    def on_status(self, info):
        self.extra.set_sensitive(info.get("installed") == "1")


class UiStreamTool(StatusTool):
    """Steam UI live view in a PC browser; the subtitle carries the URL."""

    def __init__(self, runner):
        super().__init__(runner, _("Интерфейс Steam в браузере на ПК"), "ui_stream.sh",
                         install_label=_("Включить"), remove_label=_("Выключить"),
                         actions_as_root=False)
        self.sub.set_selectable(True)

    def build_extra(self):
        btn = Gtk.Button(label=_("Копировать ссылку"))
        btn.connect("clicked", self.on_copy)
        return btn

    def on_copy(self, _btn):
        text = self.sub.get_text()
        url = text[text.find("http"):] if "http" in text else ""
        if url:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(url, -1)
            self.runner.log(_("Скопировано: {url}").format(url=url))

    def on_status(self, info):
        self.extra.set_sensitive(info.get("installed") == "1")
        self.btn_install.set_sensitive(info.get("installed") != "1")


class DeckyTool(StatusTool):
    """Decky Loader; Frame has no QAM in VR, so the panel opens as a Steam page."""

    def __init__(self, runner):
        super().__init__(runner, _("Decky Loader (ARM64, экспериментально)"), "decky.sh",
                         install_label=_("Установить / обновить"),
                         status_as_root=True, reinstall=True, repair=True)

    def build_extra(self):
        btn = Gtk.Button(label=_("Открыть в шлеме"))
        btn.connect("clicked", self.on_open)
        return btn

    def on_open(self, btn):
        self.runner.run(run_user, [tool("decky_open.py"), "panel"],
                        _("Открытие панели Decky в шлеме"), widgets=[btn])

    def on_status(self, info):
        self.extra.set_sensitive(info.get("installed") == "1")


class DeckyPlacementRow(Gtk.Box):
    """Where the SFH Frame Menu plugin shows Decky in the headset: left menu and/or Quick
    Settings (tools/decky_placement.py talks to the plugin over CDP). Both may be off."""

    def __init__(self, runner):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.runner = runner
        self.get_style_context().add_class("tool-row")
        text, self.sub = title_block(_("Где показывать Decky в шлеме"))
        self.pack_start(text, True, True, 0)
        self.checks = {}
        for key, label in (("menu", _("Левое меню")), ("qam", _("Быстрые настройки"))):
            chk = Gtk.CheckButton(label=label)
            chk.connect("toggled", self.on_toggled)
            chk.set_sensitive(False)
            self.checks[key] = chk
            self.pack_start(chk, False, False, 0)
        self.updating = False
        self.refresh()

    def show_state(self, res):
        info = parse_kv(res.stdout)
        ok = "menu" in info and "qam" in info
        self.updating = True
        for key, chk in self.checks.items():
            chk.set_sensitive(ok)
            if ok:
                chk.set_active(info[key] == "1")
        self.updating = False
        if ok:
            self.sub.set_text(_("Меню в шлеме обновится при следующем открытии"))
        else:
            self.sub.set_text(_("Нужен запущенный Steam и плагин SFH Frame Menu в Decky"))
        return False

    def refresh(self):
        threading.Thread(
            target=lambda: GLib.idle_add(
                self.show_state, run_user([tool("decky_placement.py"), "get"])),
            daemon=True).start()

    def on_toggled(self, chk):
        if self.updating:
            return
        # Both may be off: Decky is then opened only with "Open in headset" in SFH.
        menu, qam = self.checks["menu"].get_active(), self.checks["qam"].get_active()
        self.runner.run(run_user, [tool("decky_placement.py"), "set",
                                   "1" if menu else "0", "1" if qam else "0"],
                        _("Decky в шлеме: место показа"), on_done=self.show_state,
                        widgets=list(self.checks.values()))


class DeckyStoreRow(Gtk.Box):
    """Third-party Decky plugin store: pick a known address or type a new one and connect
    it, or go back to Decky's official store (tools/decky.sh store-*). Addresses that were
    connected once are remembered in ui_state.json."""

    PRESETS = ["https://repo.steamdeckbase.org/decky/plugins"]
    STATE_KEY = "decky.stores"

    def __init__(self, runner):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.runner = runner
        self.script = tool("decky.sh")
        self.get_style_context().add_class("tool-row")
        text, self.sub = title_block(_("Сторонний магазин плагинов"))
        self.pack_start(text, True, True, 0)

        self.combo = Gtk.ComboBoxText.new_with_entry()
        self.combo.set_size_request(320, -1)
        self.combo.get_child().set_placeholder_text("https://…")
        self.pack_start(self.combo, False, False, 0)
        self.btn_set = Gtk.Button(label=_("Подключить"))
        self.btn_set.connect("clicked", self.on_set)
        self.pack_start(self.btn_set, False, False, 0)
        self.btn_official = Gtk.Button(label=_("Вернуть официальный"))
        self.btn_official.connect("clicked", self.on_official)
        self.btn_official.set_sensitive(False)
        self.pack_start(self.btn_official, False, False, 0)
        self.current = ""
        self.fill([])
        self.refresh()

    def known(self):
        saved = load_ui_state().get(self.STATE_KEY, [])
        out = []
        for url in self.PRESETS + list(saved) + ([self.current] if self.current else []):
            if url and url not in out:
                out.append(url)
        return out

    def fill(self, _unused):
        typed = self.combo.get_child().get_text()
        self.combo.remove_all()
        for url in self.known():
            self.combo.append_text(url)
        self.combo.get_child().set_text(typed or self.current or self.PRESETS[0])

    def show_state(self, res):
        info = parse_kv(res.stdout)
        store, url = info.get("store", ""), info.get("url", "")
        self.current = url if store == "custom" else ""
        if store == "custom":
            self.sub.set_text(_("Подключён сторонний: {url}").format(url=url))
        elif store:
            self.sub.set_text(_("Сейчас официальный магазин Decky"))
        else:
            self.sub.set_text(_("Не удалось прочитать настройки Decky"))
        self.btn_official.set_sensitive(store == "custom")
        self.combo.get_child().set_text("")
        self.fill([])
        return False

    def refresh(self):
        threading.Thread(
            target=lambda: GLib.idle_add(self.show_state,
                                         run_user([self.script, "store-status"])),
            daemon=True).start()

    def on_set(self, _btn):
        url = self.combo.get_child().get_text().strip()
        if not (url.startswith("https://") or url.startswith("http://")):
            self.runner.log(_("Адрес магазина должен начинаться с https://"))
            return
        if not confirm(self.get_toplevel(), _("Подключить сторонний магазин?"),
                       _("Плагины из стороннего магазина не проверяет команда Decky. "
                         "Ставьте только то, чему доверяете. Decky и интерфейс Steam "
                         "перезапустятся.\n\n{url}").format(url=url)):
            return

        def done(res):
            if res.returncode == 0:
                saved = load_ui_state().get(self.STATE_KEY, [])
                if url not in saved and url not in self.PRESETS:
                    save_ui_state(self.STATE_KEY, saved + [url])
            self.refresh()

        self.runner.run(run_root, [self.script, "store-set", url],
                        _("Подключение стороннего магазина"), on_done=done,
                        widgets=[self.btn_set, self.btn_official])

    def on_official(self, _btn):
        self.runner.run(run_root, [self.script, "store-official"],
                        _("Возврат к официальному магазину"),
                        on_done=lambda _r: self.refresh(),
                        widgets=[self.btn_set, self.btn_official])


class RegionTool(StatusTool):
    def __init__(self, runner):
        super().__init__(runner, _("Поменять регион Wi-Fi"), "region.sh")

    def build_extra(self):
        combo = Gtk.ComboBoxText()
        for code, name in REGIONS:
            combo.append(code, f"{code} — {name}")
        combo.set_active_id("DE")
        return combo

    def install_args(self):
        return [self.extra.get_active_id()]

    def act(self, cmd, label):
        # With RU the Frame's hostapd can't start the SoftAP: the Steam wireless adapter
        # stops connecting (seen on a real Frame).
        if cmd == "install" and self.extra.get_active_id() == "RU" and not confirm(
                self.get_toplevel(), _("Поставить регион RU?"),
                _("С регионом RU беспроводной адаптер Steam на Steam Frame перестаёт "
                  "подключаться. Для стрима выберите другой регион.")):
            return
        super().act(cmd, label)

    def on_status(self, info):
        if info.get("configured"):
            self.extra.set_active_id(info["configured"])


class QuickActions(Gtk.Box):
    ACTIONS = [
        (_("Прервать трансляцию"), "stop-stream", False, _("Прервать трансляцию с ПК?")),
        (_("Перезапустить Steam"), "restart-steam", False, None),
        (_("Перезагрузить"), "reboot", True, _("Перезагрузить Steam Frame?")),
    ]

    def __init__(self, runner, window):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.get_style_context().add_class("tool-row")
        text, sub = title_block(_("Быстрые действия"))
        sub.set_text(_("Трансляция с ПК, Steam, перезагрузка"))
        self.pack_start(text, True, True, 0)
        for label, cmd, root, question in self.ACTIONS:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", self.on_click, runner, window, label, cmd, root, question)
            self.pack_start(btn, False, False, 0)

    @staticmethod
    def on_click(btn, runner, window, label, cmd, root, question):
        if question and not confirm(window, question):
            return
        runner.run(run_root if root else run_user, [tool("system.sh"), cmd], label,
                   widgets=[btn])


# ---------- games tab ----------

class GamesPage:
    def __init__(self, runner, window):
        self.runner = runner
        self.window = window
        self.script = tool("games.sh")
        self.widget, self.box = page()

        top = row_box()
        text, sub = title_block(_("Игры Steam"))
        sub.set_text(_("Бэкапы сохранений: ~/steam_frame_helper_backups"))
        top.pack_start(text, True, True, 0)
        refresh = Gtk.Button(label=_("Обновить"))
        refresh.connect("clicked", lambda _b: self.refresh())
        top.pack_start(refresh, False, False, 0)
        self.box.pack_start(top, False, False, 0)

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.list, False, False, 0)
        self.refresh()

    def refresh(self):
        def done(res):
            for child in self.list.get_children():
                child.destroy()
            games = parse_tsv(res.stdout, 5)
            if not games:
                self.list.pack_start(section(_("Игры не найдены")), False, False, 0)
            for appid, name, kind, shader, backups in games:
                self.list.pack_start(self.game_row(appid, name, kind, shader,
                                                   int(backups)), False, False, 0)
            self.list.show_all()
            return False

        threading.Thread(
            target=lambda: GLib.idle_add(done, run_user([self.script, "list"])),
            daemon=True,
        ).start()

    KINDS = {
        "proton": "Windows (Proton)",
        "android": "Android",
        "native": "Linux",
    }

    def game_row(self, appid, name, kind, shader, backups):
        box = row_box()
        text, sub = title_block(name)
        has_prefix = kind in ("proton", "android")
        sub.set_text(_("AppID {appid}  ·  {kind}  ·  шейдеры: {shader}  ·  бэкапов: {backups}")
                     .format(appid=appid, kind=self.KINDS.get(kind, kind),
                             shader=shader, backups=backups))
        box.pack_start(text, True, True, 0)

        buttons = []

        def add(label, handler, sensitive=True, danger=False):
            btn = Gtk.Button(label=label)
            btn.set_sensitive(sensitive)
            if danger:
                btn.get_style_context().add_class("danger")
            btn.connect("clicked", lambda _b: handler(appid, name, buttons))
            box.pack_start(btn, False, False, 0)
            buttons.append(btn)

        add(_("Бэкап"), self.backup)
        add(_("Восстановить"), self.restore, sensitive=backups > 0)
        add(_("Очистить шейдеры"), self.clear_shaders, sensitive=shader != "-")
        add(_("Сбросить префикс"), self.reset_prefix, sensitive=has_prefix, danger=True)
        return box

    def _run(self, args, message, buttons):
        self.runner.run(run_user, [self.script] + args, message,
                        on_done=lambda _r: self.refresh(), widgets=buttons)

    def backup(self, appid, name, buttons):
        self._run(["backup", appid], _("Бэкап сохранений: {name}").format(name=name), buttons)

    def restore(self, appid, name, buttons):
        files = run_user([self.script, "backups", appid]).stdout.split()
        if not files:
            return
        dlg = Gtk.Dialog(title=_("Восстановить: {name}").format(name=name), transient_for=self.window, modal=True)
        dlg.add_buttons(_("Отмена"), Gtk.ResponseType.CANCEL, _("Восстановить"), Gtk.ResponseType.OK)
        area = dlg.get_content_area()
        area.set_spacing(8)
        area.set_margin_start(12)
        area.set_margin_end(12)
        area.pack_start(Gtk.Label(
            label=_("Текущие сохранения будут перезаписаны. Игра должна быть закрыта."),
            xalign=0), False, False, 0)
        combo = Gtk.ComboBoxText()
        for f in files:
            combo.append(f, os.path.basename(f).replace(".tar.gz", ""))
        combo.set_active(0)
        area.pack_start(combo, False, False, 0)
        dlg.show_all()
        ok = dlg.run() == Gtk.ResponseType.OK
        chosen = combo.get_active_id()
        dlg.destroy()
        if ok and chosen:
            self._run(["restore", appid, chosen], _("Восстановление: {name}").format(name=name), buttons)

    def clear_shaders(self, appid, name, buttons):
        if confirm(self.window, _("Очистить шейдер-кэш «{name}»?").format(name=name),
                   _("Кэш соберётся заново при следующем запуске, первые минуты игра может подтормаживать.")):
            self._run(["clear-shaders", appid], _("Очистка шейдеров: {name}").format(name=name), buttons)

    def reset_prefix(self, appid, name, buttons):
        if confirm(self.window, _("Сбросить данные «{name}»?").format(name=name),
                   _("Удаляется префикс Proton или данные Android-приложения. Перед удалением "
                     "будет сделан бэкап сохранений. Настройки игры и установленные в префикс "
                     "библиотеки пропадут, Steam создаст всё заново при запуске.")):
            self._run(["reset-prefix", appid], _("Сброс префикса: {name}").format(name=name), buttons)


# ---------- decky plugins tab ----------

class PluginsPage:
    """Installed Decky plugins: enable/disable, update from store, remove."""

    def __init__(self, runner, window):
        self.runner = runner
        self.window = window
        self.script = tool("decky_plugins.py")
        self.widget, outer = page()

        loader = Section("plugins.loader", "Decky Loader")
        outer.pack_start(loader, False, False, 0)
        loader.add_row(DeckyTool(runner))
        loader.add_row(DeckyPlacementRow(runner))
        loader.add_row(DeckyStoreRow(runner))
        installed = Section("plugins.installed", _("Установленные плагины"))
        outer.pack_start(installed, False, False, 0)
        self.box = installed.body

        top = row_box()
        text, self.summary = title_block(_("Плагины Decky"))
        self.summary.set_text("~/homebrew/plugins")
        top.pack_start(text, True, True, 0)
        for label, handler in (
            (_("Обновить список"), lambda _b: self.refresh()),
            (_("Магазин в шлеме"), lambda b: self.open_in_headset(b, "store")),
            (_("Панель в шлеме"), lambda b: self.open_in_headset(b, "panel")),
        ):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", handler)
            top.pack_start(btn, False, False, 0)
        self.box.pack_start(top, False, False, 0)

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.list, False, False, 0)
        self.refresh()

    def open_in_headset(self, btn, target):
        self.runner.run(run_user, [tool("decky_open.py"), target],
                        _("Открытие Decky в шлеме"), widgets=[btn])

    def refresh(self):
        self.summary.set_text(_("Загрузка списка и проверка обновлений…"))

        def done(res):
            for child in self.list.get_children():
                child.destroy()
            plugins = parse_tsv(res.stdout, 5)
            updates = sum(1 for p in plugins if p[4])
            self.summary.set_text(_("Установлено: {n}  ·  обновлений: {u}").format(n=len(plugins), u=updates))
            if not plugins:
                self.list.pack_start(section(_("Плагины не установлены")), False, False, 0)
            for folder, name, version, disabled, latest in plugins:
                self.list.pack_start(self.plugin_row(folder, name, version,
                                                     disabled == "1", latest), False, False, 0)
            self.list.show_all()
            return False

        threading.Thread(
            target=lambda: GLib.idle_add(done, run_user([self.script, "list"])),
            daemon=True,
        ).start()

    def plugin_row(self, folder, name, version, disabled, latest):
        box = row_box()
        mark = Gtk.Label(label="✖" if disabled else "✔")
        mark.set_size_request(36, -1)
        mark.get_style_context().add_class("status-no" if disabled else "status-ok")
        box.pack_start(mark, False, False, 0)

        text, sub = title_block(name)
        state = _("отключён") if disabled else _("включён")
        update = _("  ·  доступно обновление: {latest}").format(latest=latest) if latest else ""
        sub.set_text(_("версия {version}  ·  {state}{update}").format(
            version=version, state=state, update=update))
        box.pack_start(text, True, True, 0)

        buttons = []

        def add(label, args, message, sensitive=True, danger=False, question=None):
            btn = Gtk.Button(label=label)
            btn.set_sensitive(sensitive)
            if danger:
                btn.get_style_context().add_class("danger")

            def clicked(_b):
                if question and not confirm(self.window, question[0], question[1]):
                    return
                self.runner.run(run_root, [self.script] + args, message,
                                on_done=lambda _r: self.refresh(), widgets=buttons)

            btn.connect("clicked", clicked)
            box.pack_start(btn, False, False, 0)
            buttons.append(btn)

        if disabled:
            add(_("Включить"), ["enable", folder], _("Включение {name}").format(name=name))
        else:
            add(_("Отключить"), ["disable", folder], _("Отключение {name}").format(name=name))
        add(T("Обновить", "Update"), ["update", folder], _("Обновление {name}").format(name=name),
            sensitive=bool(latest))
        add(_("Удалить"), ["remove", folder], _("Удаление {name}").format(name=name), danger=True,
            question=(_("Удалить плагин «{name}»?").format(name=name),
                      _("Папка плагина будет удалена. Decky перезапустится.")))
        return box


# ---------- log viewer ----------

def strip_ansi(text):
    """Removes terminal colour sequences (ESC [ params letter) — logcat colours its output."""
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "\x1b" and i + 1 < n and text[i + 1] == "[":
            j = i + 2
            while j < n and (text[j].isdigit() or text[j] == ";"):
                j += 1
            i = j + 1 if j < n else j   # skip the final letter (m, K, ...)
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


class LogViewer(Gtk.Window):
    """Shows the tail of a log file: SteamOS on Frame ships no GUI text editor."""

    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, parent, title, path, open_path):
        super().__init__(title=_("Лог: {title}").format(title=title))
        self.path = path
        self.set_transient_for(parent)
        self.set_default_size(1000, 640)

        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        headerbar.set_title(_("Лог: {title}").format(title=title))
        headerbar.set_subtitle(path)
        self.set_titlebar(headerbar)
        btn_reload = Gtk.Button(label=_("Обновить"))
        btn_reload.connect("clicked", lambda _b: self.load())
        headerbar.pack_start(btn_reload)
        btn_dir = Gtk.Button(label=_("Папка логов"))
        btn_dir.connect("clicked", lambda _b: open_path(os.path.dirname(path)))
        headerbar.pack_start(btn_dir)

        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_monospace(True)
        self.view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.add(self.view)
        self.add(self.scroll)
        self.load()
        self.show_all()

    def load(self):
        try:
            with open(self.path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - self.MAX_BYTES))
                data = f.read()
            text = strip_ansi(data.decode("utf-8", "replace"))
            if size > self.MAX_BYTES:
                text = _("… показаны последние {shown} МБ из {total} МБ …").format(
                    shown=self.MAX_BYTES // 1024 // 1024, total=size // 1024 // 1024) + "\n" + text
        except OSError as e:
            text = _("Не удалось прочитать {path}: {error}").format(path=self.path, error=e)
        buf = self.view.get_buffer()
        buf.set_text(text)
        # newest entries are at the end
        GLib.idle_add(lambda: self.view.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 1) and False)


# ---------- android apps tab ----------

class AndroidPage:
    """APK (+OBB) as Steam library VR apps through Lepton (tools/android_app.py)."""

    def __init__(self, runner, window):
        self.runner = runner
        self.window = window
        self.script = tool("android_app.py")
        self.apk = None
        self.obbs = []
        self.widget, self.box = page()

        self.box.pack_start(section(_("Установить APK")), False, False, 0)
        form = row_box()
        form.set_orientation(Gtk.Orientation.VERTICAL)
        form.set_spacing(8)

        name_row = Gtk.Box(spacing=8)
        name_row.pack_start(Gtk.Label(label=_("Название в библиотеке:"), xalign=0), False, False, 0)
        self.name = Gtk.Entry()
        self.name.set_placeholder_text(_("например, Моя игра"))
        name_row.pack_start(self.name, True, True, 0)
        form.pack_start(name_row, False, False, 0)

        apk_row = Gtk.Box(spacing=8)
        self.apk_label = Gtk.Label(label=_("APK не выбран"), xalign=0)
        self.apk_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.apk_label.get_style_context().add_class("tool-sub")
        btn_apk = Gtk.Button(label=_("Выбрать APK…"))
        btn_apk.connect("clicked", self.choose_apk)
        apk_row.pack_start(btn_apk, False, False, 0)
        apk_row.pack_start(self.apk_label, True, True, 0)
        form.pack_start(apk_row, False, False, 0)

        obb_row = Gtk.Box(spacing=8)
        self.obb_label = Gtk.Label(label=_("OBB нет (необязательно)"), xalign=0)
        self.obb_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.obb_label.get_style_context().add_class("tool-sub")
        btn_obb = Gtk.Button(label=_("Выбрать OBB…"))
        btn_obb.connect("clicked", self.choose_obbs)
        obb_row.pack_start(btn_obb, False, False, 0)
        obb_row.pack_start(self.obb_label, True, True, 0)
        form.pack_start(obb_row, False, False, 0)

        lepton_row = Gtk.Box(spacing=8)
        lepton_row.pack_start(Gtk.Label(label=_("Среда Android:"), xalign=0), False, False, 0)
        self.lepton = Gtk.ComboBoxText()
        self.lepton.append("auto", _("Авто (по minSdk из APK)"))
        self.lepton.append("11", "Lepton — Android 11 (SDK 30)")
        self.lepton.append("14", "Lepton 14 — Android 14 (SDK 34)")
        self.lepton.set_active_id("auto")
        lepton_row.pack_start(self.lepton, False, False, 0)
        self.apk_info = Gtk.Label(label="", xalign=0)
        self.apk_info.set_ellipsize(Pango.EllipsizeMode.END)
        self.apk_info.get_style_context().add_class("tool-sub")
        lepton_row.pack_start(self.apk_info, True, True, 0)
        form.pack_start(lepton_row, False, False, 0)

        action_row = Gtk.Box(spacing=8)
        hint = Gtk.Label(
            label=_("Приложение появится в библиотеке Steam и запустится через Lepton. "
                    "Steam перезапустится."), xalign=0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("tool-sub")
        action_row.pack_start(hint, True, True, 0)
        self.btn_install = Gtk.Button(label=_("Установить"))
        self.btn_install.connect("clicked", self.install)
        action_row.pack_start(self.btn_install, False, False, 0)
        form.pack_start(action_row, False, False, 0)
        self.box.pack_start(form, False, False, 0)

        self.box.pack_start(section(_("Установленные")), False, False, 0)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.list, False, False, 0)
        self.refresh()

    def _chooser(self, title, pattern, multiple):
        dlg = Gtk.FileChooserDialog(title=title, transient_for=self.window,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons(_("Отмена"), Gtk.ResponseType.CANCEL, _("Выбрать"), Gtk.ResponseType.OK)
        dlg.set_select_multiple(multiple)
        dlg.set_current_folder(os.path.expanduser("~/Downloads"))
        flt = Gtk.FileFilter()
        flt.set_name(pattern)
        flt.add_pattern(pattern)
        flt.add_pattern(pattern.upper())
        dlg.add_filter(flt)
        files = dlg.get_filenames() if dlg.run() == Gtk.ResponseType.OK else []
        dlg.destroy()
        return files

    def choose_apk(self, _btn):
        files = self._chooser(_("Выберите APK"), "*.apk", False)
        if files:
            self.apk = files[0]
            self.apk_label.set_text(self.apk)
            if not self.name.get_text().strip():
                self.name.set_text(os.path.splitext(os.path.basename(self.apk))[0])
            self.show_apk_info()

    def show_apk_info(self):
        self.apk_info.set_text(_("Чтение APK…"))
        apk = self.apk

        def done(res):
            info = parse_kv(res.stdout)
            if res.returncode != 0 or not info.get("min_sdk"):
                self.apk_info.set_text(_("Не удалось прочитать APK"))
                return False
            env = "Lepton 14" if info.get("lepton") == "14" else "Lepton (Android 11)"
            self.apk_info.set_text(
                _("{app_id}  ·  minSdk {min_sdk}  ·  авто: {env}").format(
                    app_id=info.get("app_id", "?"), min_sdk=info["min_sdk"], env=env))
            return False

        threading.Thread(
            target=lambda: GLib.idle_add(done, run_user([self.script, "info", apk])),
            daemon=True,
        ).start()

    def choose_obbs(self, _btn):
        self.obbs = self._chooser(_("Выберите OBB (можно несколько)"), "*.obb", True)
        self.obb_label.set_text(", ".join(os.path.basename(f) for f in self.obbs)
                                if self.obbs else _("OBB нет (необязательно)"))

    def install(self, _btn):
        name = self.name.get_text().strip()
        if not name or not self.apk:
            self.runner.log(_("Укажи название и выбери APK"))
            return
        if "/" in name:
            self.runner.log(_("Название не должно содержать «/»"))
            return
        if not confirm(self.window, _("Установить «{name}»?").format(name=name),
                       _("Steam перезапустится, в шлеме это займёт около полуминуты.")):
            return
        args = ([self.script, "install", name, self.apk] + self.obbs
                + ["--lepton", self.lepton.get_active_id() or "auto"])
        self.runner.run(run_user, args, _("Установка {name}").format(name=name),
                        on_done=lambda _r: self.refresh(), widgets=[self.btn_install])

    def refresh(self):
        def done(res):
            for child in self.list.get_children():
                child.destroy()
            apps = parse_tsv(res.stdout, 8)
            if not apps:
                self.list.pack_start(section(_("Пока ничего не установлено")), False, False, 0)
            for name, apk, obbs, size, container, tool_name, _appid, log in apps:
                self.list.pack_start(self.app_row(name, apk, obbs, size, container == "1",
                                                  tool_name, log), False, False, 0)
            self.list.show_all()
            return False

        threading.Thread(
            target=lambda: GLib.idle_add(done, run_user([self.script, "list"])),
            daemon=True,
        ).start()

    def app_row(self, name, apk, obbs, size, has_container, tool_name, log):
        box = row_box()
        text, sub = title_block(name)
        state = _("запускался") if has_container else _("ещё не запускался")
        env = {"lepton": "Lepton (Android 11)", "lepton_14": "Lepton 14"}.get(tool_name, tool_name)
        folder = os.path.dirname(apk)
        sub.set_text(_("{env}  ·  {size} МБ  ·  OBB: {obbs}  ·  {state}  ·  {folder}").format(
            env=env, size=size, obbs=obbs, state=state, folder=folder))
        box.pack_start(text, True, True, 0)

        btn_log = Gtk.Button(label=_("Лог"))
        btn_log.set_sensitive(bool(log))
        btn_log.set_tooltip_text(log or _("Лога пока нет: приложение ещё не запускалось"))
        btn_log.connect("clicked", lambda _b: LogViewer(self.window, name, log, self.open_path))
        box.pack_start(btn_log, False, False, 0)

        btn_dir = Gtk.Button(label=_("Папка"))
        btn_dir.set_tooltip_text(folder)
        btn_dir.connect("clicked", lambda _b: self.open_path(folder))
        box.pack_start(btn_dir, False, False, 0)

        btn = Gtk.Button(label=_("Удалить"))
        btn.get_style_context().add_class("danger")
        btn.connect("clicked", lambda _b: self.remove(name, btn))
        box.pack_start(btn, False, False, 0)
        return box

    def open_path(self, path):
        """Opens a file or folder in the default desktop app (Kate, Dolphin, ...)."""
        if not path or not os.path.exists(path):
            self.runner.log(_("Не найдено: {path}").format(path=path))
            return
        try:
            subprocess.Popen(["xdg-open", path], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.runner.log(_("Открыто: {path}").format(path=path))
        except OSError as e:
            self.runner.log(_("Не удалось открыть {path}: {error}").format(path=path, error=e))

    def remove(self, name, btn):
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.NONE,
                                text=_("Удалить «{name}» из библиотеки?").format(name=name))
        dlg.format_secondary_text(
            _("Контейнер Lepton с сохранениями останется. Steam перезапустится."))
        dlg.add_buttons(_("Отмена"), Gtk.ResponseType.CANCEL,
                        _("Только ярлык"), 1, _("Ярлык и файлы"), 2)
        resp = dlg.run()
        dlg.destroy()
        if resp not in (1, 2):
            return
        args = [self.script, "remove", name] + (["--purge"] if resp == 2 else [])
        self.runner.run(run_user, args, _("Удаление {name}").format(name=name),
                        on_done=lambda _r: self.refresh(), widgets=[btn])


# ---------- transfer to PC tab ----------

def human_size(n):
    for unit, step in ((_("ГБ"), 1 << 30), (_("МБ"), 1 << 20), (_("КБ"), 1 << 10)):
        if n >= step:
            return f"{n / step:.1f} {unit}"
    return f"{n} {_('Б')}"


class TransferPage:
    """Files/folders from the Frame to the PC: queued here, pulled by the PC agent."""

    def __init__(self, runner, window):
        self.runner = runner
        self.window = window
        self.script = tool("to_pc.py")
        self.widget, outer = page()

        shots = Section("transfer.screenshots", _("Скриншоты"))
        outer.pack_start(shots, False, False, 0)
        shots.add_row(StatusTool(runner, _("Копировать скриншоты на Frame (Pictures/Screenshots)"),
                                 "screenshots_local.sh", install_label=_("Включить"),
                                 remove_label=_("Выключить"), actions_as_root=False))
        shots.add_row(StatusTool(runner, _("Копировать скриншоты на ПК (Изображения\\SteamFrame)"),
                                 "screenshots_pc.sh", install_label=_("Включить"),
                                 remove_label=_("Выключить"), actions_as_root=False))
        files = Section("transfer.files", _("Файлы на ПК"))
        outer.pack_start(files, False, False, 0)
        self.box = files.body

        top = row_box()
        text, self.agent = title_block(_("Отправить на ПК (Загрузки\\SteamFrame)"))
        top.pack_start(text, True, True, 0)
        for label, handler in ((_("Файлы…"), self.pick_files), (_("Папка…"), self.pick_folder)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", handler)
            top.pack_start(btn, False, False, 0)
        self.box.pack_start(top, False, False, 0)

        hint = Gtk.Label(
            label=_("Агент на ПК забирает очередь каждые 5 секунд. Если ПК выключен, "
                    "файлы подождут в очереди. Большие файлы не занимают лишнего места: "
                    "в очередь кладутся жёсткие ссылки."), xalign=0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("tool-sub")
        hint.set_margin_start(16)
        hint.set_margin_end(16)
        self.box.pack_start(hint, False, False, 0)

        head = Gtk.Box(spacing=8)
        head.pack_start(section(_("Очередь")), True, True, 0)
        btn_clear = Gtk.Button(label=_("Очистить очередь"))
        btn_clear.set_margin_end(12)
        btn_clear.connect("clicked", self.clear)
        head.pack_start(btn_clear, False, False, 0)
        self.box.pack_start(head, False, False, 0)
        self.queue = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.queue, False, False, 0)

        self.refresh()
        GLib.timeout_add_seconds(3, self.tick)

    def tick(self):
        if self.widget.get_mapped():
            self.refresh()
        return True

    def pick(self, title, action):
        dlg = Gtk.FileChooserDialog(title=title, transient_for=self.window, action=action)
        dlg.add_buttons(_("Отмена"), Gtk.ResponseType.CANCEL, _("Отправить"), Gtk.ResponseType.OK)
        dlg.set_select_multiple(True)
        dlg.set_current_folder(os.path.expanduser("~"))
        paths = dlg.get_filenames() if dlg.run() == Gtk.ResponseType.OK else []
        dlg.destroy()
        if paths:
            self.runner.run(run_user, [self.script, "add"] + paths,
                            _("В очередь на ПК: {n}").format(n=len(paths)), on_done=lambda _r: self.refresh())

    def pick_files(self, _btn):
        self.pick(_("Файлы для отправки на ПК"), Gtk.FileChooserAction.OPEN)

    def pick_folder(self, _btn):
        self.pick(_("Папки для отправки на ПК"), Gtk.FileChooserAction.SELECT_FOLDER)

    def clear(self, _btn):
        if confirm(self.window, _("Очистить очередь?"),
                   _("Файлы, которые ещё не ушли на ПК, будут убраны из очереди. "
                     "Оригиналы на Frame не пострадают.")):
            self.runner.run(run_user, [self.script, "clear"], _("Очистка очереди"),
                            on_done=lambda _r: self.refresh())

    def refresh(self):
        def done(listing, status):
            age = int(status.stdout.strip() or -1)
            if age < 0:
                self.agent.set_text(_("Агент на ПК ещё не подключался"))
            elif age < 30:
                self.agent.set_text(_("ПК на связи ({age} с назад)").format(age=age))
            else:
                self.agent.set_text(_("ПК не на связи {min} мин — включён ли ПК и агент?").format(min=age // 60))
            for child in self.queue.get_children():
                child.destroy()
            items = parse_tsv(listing.stdout, 2)
            if not items:
                self.queue.pack_start(section(_("Пусто — всё доставлено")), False, False, 0)
            for name, size in items:
                box = row_box()
                t, sub = title_block(name)
                sub.set_text(_("{size}  ·  ждёт, пока ПК заберёт").format(size=human_size(int(size))))
                box.pack_start(t, True, True, 0)
                self.queue.pack_start(box, False, False, 0)
            self.queue.show_all()
            return False

        def work():
            listing = run_user([self.script, "list"])
            status = run_user([self.script, "status"])
            GLib.idle_add(done, listing, status)

        threading.Thread(target=work, daemon=True).start()


# ---------- apps tab ----------

class AppsPage:
    def __init__(self, runner, window):
        self.runner = runner
        self.window = window
        self.script = tool("flatpak.sh")
        self.widget, self.box = page()

        top = row_box()
        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text(_("Поиск на Flathub: telegram, firefox, vlc…"))
        self.entry.connect("activate", lambda _e: self.search())
        top.pack_start(self.entry, True, True, 0)
        self.btn_search = Gtk.Button(label=_("Найти"))
        self.btn_search.connect("clicked", lambda _b: self.search())
        top.pack_start(self.btn_search, False, False, 0)
        fix = Gtk.Button(label=_("Починить Flathub"))
        fix.connect("clicked", self.fix_flathub)
        top.pack_start(fix, False, False, 0)
        self.box.pack_start(top, False, False, 0)

        self.box.pack_start(section(_("Результаты поиска")), False, False, 0)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.results, False, False, 0)

        self.box.pack_start(section(_("Установлено")), False, False, 0)
        self.installed = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.installed, False, False, 0)

        self.installed_ids = set()
        self.refresh_installed()

    @staticmethod
    def clear(box):
        for child in box.get_children():
            child.destroy()

    def app_row(self, app_id, name, detail, installed):
        box = row_box()
        text, sub = title_block(name)
        sub.set_text(f"{app_id}  ·  {detail}" if detail else app_id)
        box.pack_start(text, True, True, 0)
        if installed:
            btn = Gtk.Button(label=_("Удалить"))
            btn.connect("clicked", lambda _b: self.remove(app_id, name, btn))
        else:
            btn = Gtk.Button(label=_("Установить"))
            btn.connect("clicked", lambda _b: self.install(app_id, name, btn))
        box.pack_start(btn, False, False, 0)
        return box

    def refresh_installed(self):
        def done(res):
            self.clear(self.installed)
            apps = parse_tsv(res.stdout, 3)
            self.installed_ids = {a[0] for a in apps}
            for app_id, name, version in apps:
                self.installed.pack_start(self.app_row(app_id, name, version, True),
                                          False, False, 0)
            if not apps:
                self.installed.pack_start(section(_("Ничего не установлено")), False, False, 0)
            self.installed.show_all()
            return False

        threading.Thread(
            target=lambda: GLib.idle_add(done, run_user([self.script, "list"])),
            daemon=True,
        ).start()

    def search(self):
        query = self.entry.get_text().strip()
        if not query:
            return

        def done(res):
            self.clear(self.results)
            apps = parse_tsv(res.stdout, 3)[:30]
            for app_id, name, desc in apps:
                self.results.pack_start(
                    self.app_row(app_id, name, desc, app_id in self.installed_ids),
                    False, False, 0)
            if not apps:
                self.results.pack_start(section(_("Ничего не найдено")), False, False, 0)
            self.results.show_all()

        self.runner.run(run_user, [self.script, "search", query], _("Поиск «{query}»").format(query=query),
                        on_done=done, widgets=[self.btn_search])

    def install(self, app_id, name, btn):
        def done(_res):
            self.refresh_installed()
            self.search()

        self.runner.run(run_root, [self.script, "install", app_id], _("Установка {name}").format(name=name),
                        on_done=done, widgets=[btn])

    def remove(self, app_id, name, btn):
        if not confirm(self.window, _("Удалить {name}?").format(name=name),
                   _("Данные приложения в ~/.var/app останутся.")):
            return
        self.runner.run(run_root, [self.script, "remove", app_id], _("Удаление {name}").format(name=name),
                        on_done=lambda _r: self.refresh_installed(), widgets=[btn])

    def fix_flathub(self, btn):
        self.runner.run(run_root, [self.script, "fix-flathub"], _("Починка Flathub"),
                        widgets=[btn])


# ---------- main window ----------

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Steam Frame Helper")
        self.set_default_size(1000, 620)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Client-side title bar: GTK3 gets no system decorations on Frame.
        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        headerbar.set_decoration_layout("menu:minimize,maximize,close")
        headerbar.set_title("Steam Frame Helper")
        headerbar.set_subtitle(_("версия {version}").format(version=VERSION))
        self.set_titlebar(headerbar)

        lang_combo = Gtk.ComboBoxText()
        for code, name in LANGUAGES:
            lang_combo.append(code, name)
        lang_combo.set_active_id(LANG)
        lang_combo.connect("changed", self.on_language_changed)
        headerbar.pack_end(lang_combo)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        self.status = Gtk.Label(label="", xalign=0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        full_text_tooltip(self.status)
        self.status.get_style_context().add_class("log")
        runner = Runner(self.log)

        notebook = Gtk.Notebook()
        root.pack_start(notebook, True, True, 0)
        root.pack_start(self.status, False, False, 0)

        tools_page, tools = page()
        net = Section("tools.network", _("Сеть"))
        tools.pack_start(net, False, False, 0)
        # AmneziaVPN is not part of the public release; the row appears only where its
        # scripts were added by hand (tools/amneziavpn.sh).
        if os.path.exists(tool("amneziavpn.sh")):
            net.add_row(StatusTool(runner, _("AmneziaVPN (нативная сборка ARM64)"), "amneziavpn.sh",
                                   install_label=_("Установить / обновить"),
                                   reinstall=True, repair=True))
        net.add_row(RegionTool(runner))
        net.add_row(StatusTool(runner, _("Wi-Fi без энергосбережения"), "wifi.sh",
                               install_label=_("Выключить"), remove_label=_("Включить")))
        net.add_row(VrHudTool(runner))
        system = Section("tools.system", _("Система"))
        tools.pack_start(system, False, False, 0)
        system.add_row(StatusTool(runner, _("Запись в системный раздел"), "readonly.sh",
                                  install_label=_("Разблокировать"),
                                  remove_label=_("Заблокировать"),
                                  status_as_root=True))
        system.add_row(StatusTool(runner, _("Права администратора без пароля"), "sudo_nopasswd.sh",
                                  install_label=_("Включить"), remove_label=_("Выключить")))
        system.add_row(QuickActions(runner, self))
        notebook.append_page(tools_page, Gtk.Label(label=_("Инструменты")))

        notebook.append_page(PluginsPage(runner, self).widget, Gtk.Label(label=_("Плагины")))
        notebook.append_page(GamesPage(runner, self).widget, Gtk.Label(label=_("Игры")))
        notebook.append_page(AppsPage(runner, self).widget, Gtk.Label(label=_("Приложения")))
        notebook.append_page(AndroidPage(runner, self).widget, Gtk.Label(label="Android"))
        notebook.append_page(TransferPage(runner, self).widget, Gtk.Label(label=_("Передача")))

        dev_page, dev = page()
        view = Section("dev.view", _("Просмотр"))
        dev.pack_start(view, False, False, 0)
        view.add_row(UiStreamTool(runner))
        remote = Section("dev.remote", _("Удалённый доступ"))
        dev.pack_start(remote, False, False, 0)
        remote.add_row(StatusTool(runner, _("RDP: Wi-Fi без запроса пароля"), "rdp_wifi_scan.sh",
                                  install_label=_("Включить"), remove_label=_("Выключить"),
                                  status_as_root=True))
        notebook.append_page(dev_page, Gtk.Label(label=_("Разработка")))

    def log(self, text):
        self.status.set_text(text)

    @staticmethod
    def on_language_changed(combo):
        code = combo.get_active_id()
        if not code or code == LANG:
            return
        save_ui_state("language", code)
        try:
            # the background HUD reads the language at start
            subprocess.run(["systemctl", "--user", "try-restart", "sfh-vr-hud.service"],
                           capture_output=True, env=user_session_env())
        except OSError:
            pass
        os.environ["SFH_LANG"] = code
        os.execv(sys.executable, [sys.executable] + sys.argv)


def main():
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-application-prefer-dark-theme", True)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
