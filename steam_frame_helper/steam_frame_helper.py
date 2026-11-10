#!/usr/bin/env python3
"""Steam Frame Helper: GTK3 utility with system tweaks for Steam Frame."""

import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(APP_DIR, "tools")
try:
    with open(os.path.join(APP_DIR, "VERSION"), encoding="utf-8") as _f:
        VERSION = _f.read().strip()
except OSError:
    VERSION = "dev"

REGIONS = [
    ("DE", "Германия"),
    ("PL", "Польша"),
    ("FI", "Финляндия"),
    ("NL", "Нидерланды"),
    ("FR", "Франция"),
    ("GB", "Великобритания"),
    ("US", "США"),
    ("RU", "Россия"),
]

CSS = b"""
window { background-color: #1b1e24; color: #e6e6e6; }
.tool-row { background-color: #242830; border-radius: 8px; padding: 12px; margin: 6px 12px; }
.section { font-size: 13px; font-weight: bold; color: #8b949e; margin: 14px 16px 2px 16px; }
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


def run_user(args):
    return subprocess.run(args, capture_output=True, text=True)


def run_root(args):
    """Run as root: passwordless sudo first, pkexec as fallback."""
    for prefix in (["sudo", "-n"], ["pkexec"]):
        try:
            res = subprocess.run(prefix + args, capture_output=True, text=True)
        except FileNotFoundError:
            continue
        if prefix[0] == "sudo" and res.returncode != 0 and "password" in res.stderr:
            continue
        return res
    return subprocess.CompletedProcess(args, 1, "", "Нет прав root (sudo/pkexec)")


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
    return text.splitlines()[-1] if text else f"код {res.returncode}"


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
                self.log(message + " — готово")
            else:
                self.log(f"{message} — ошибка: {error_text(res)}")
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

    def __init__(self, runner, title, script, install_label="Установить",
                 remove_label="Удалить", status_as_root=False, reinstall=False,
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
            self.btn_repair = Gtk.Button(label="Починить")
            self.btn_repair.connect("clicked", lambda _b: self.act("repair", "Починить"))
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

        func = run_root if self.status_as_root else run_user
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
    """VR HUD with network/streaming stats: install = autostart service; extra button toggles."""

    def __init__(self, runner):
        super().__init__(runner, "VR HUD: сеть и стрим в шлеме", "vr_hud.sh",
                         install_label="Включить", remove_label="Выключить",
                         actions_as_root=False)

    def build_extra(self):
        btn = Gtk.Button(label="Показать / скрыть")
        btn.connect("clicked", lambda _b: self.runner.run(
            run_user, [self.script, "toggle"], f"{self.title}: показать / скрыть",
            widgets=self.widgets()))
        return btn

    def on_status(self, info):
        self.extra.set_sensitive(info.get("installed") == "1")


class UiStreamTool(StatusTool):
    """Steam UI live view in a PC browser; the subtitle carries the URL."""

    def __init__(self, runner):
        super().__init__(runner, "Интерфейс Steam в браузере на ПК", "ui_stream.sh",
                         install_label="Включить", remove_label="Выключить",
                         actions_as_root=False)
        self.sub.set_selectable(True)

    def build_extra(self):
        btn = Gtk.Button(label="Копировать ссылку")
        btn.connect("clicked", self.on_copy)
        return btn

    def on_copy(self, _btn):
        text = self.sub.get_text()
        url = text[text.find("http"):] if "http" in text else ""
        if url:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(url, -1)
            self.runner.log(f"Скопировано: {url}")

    def on_status(self, info):
        self.extra.set_sensitive(info.get("installed") == "1")
        self.btn_install.set_sensitive(info.get("installed") != "1")


class DeckyTool(StatusTool):
    """Decky Loader; Frame has no QAM in VR, so the panel opens as a Steam page."""

    def __init__(self, runner):
        super().__init__(runner, "Decky Loader (ARM64, экспериментально)", "decky.sh",
                         install_label="Установить / обновить",
                         status_as_root=True, reinstall=True, repair=True)

    def build_extra(self):
        btn = Gtk.Button(label="Открыть в шлеме")
        btn.connect("clicked", self.on_open)
        return btn

    def on_open(self, btn):
        self.runner.run(run_user, [tool("decky_open.py"), "panel"],
                        "Открытие панели Decky в шлеме", widgets=[btn])

    def on_status(self, info):
        self.extra.set_sensitive(info.get("installed") == "1")


class RegionTool(StatusTool):
    def __init__(self, runner):
        super().__init__(runner, "Поменять регион Wi-Fi", "region.sh")

    def build_extra(self):
        combo = Gtk.ComboBoxText()
        for code, name in REGIONS:
            combo.append(code, f"{code} — {name}")
        combo.set_active_id("DE")
        return combo

    def install_args(self):
        return [self.extra.get_active_id()]

    def on_status(self, info):
        if info.get("configured"):
            self.extra.set_active_id(info["configured"])


class QuickActions(Gtk.Box):
    ACTIONS = [
        ("Перезапустить Steam", "restart-steam", False, None),
        ("Рабочий стол", "desktop", False, "Переключиться в режим рабочего стола?"),
        ("Игровой режим", "gamemode", False, "Переключиться в игровой режим?"),
        ("Перезагрузить", "reboot", True, "Перезагрузить Steam Frame?"),
    ]

    def __init__(self, runner, window):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.get_style_context().add_class("tool-row")
        text, sub = title_block("Быстрые действия")
        sub.set_text("Steam, режимы, перезагрузка")
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
        text, sub = title_block("Игры Steam")
        sub.set_text("Бэкапы сохранений: ~/steam_frame_helper_backups")
        top.pack_start(text, True, True, 0)
        refresh = Gtk.Button(label="Обновить")
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
                self.list.pack_start(section("Игры не найдены"), False, False, 0)
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
        sub.set_text(f"AppID {appid}  ·  {self.KINDS.get(kind, kind)}  ·  "
                     f"шейдеры: {shader}  ·  бэкапов: {backups}")
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

        add("Бэкап", self.backup)
        add("Восстановить", self.restore, sensitive=backups > 0)
        add("Очистить шейдеры", self.clear_shaders, sensitive=shader != "-")
        add("Сбросить префикс", self.reset_prefix, sensitive=has_prefix, danger=True)
        return box

    def _run(self, args, message, buttons):
        self.runner.run(run_user, [self.script] + args, message,
                        on_done=lambda _r: self.refresh(), widgets=buttons)

    def backup(self, appid, name, buttons):
        self._run(["backup", appid], f"Бэкап сохранений: {name}", buttons)

    def restore(self, appid, name, buttons):
        files = run_user([self.script, "backups", appid]).stdout.split()
        if not files:
            return
        dlg = Gtk.Dialog(title=f"Восстановить: {name}", transient_for=self.window, modal=True)
        dlg.add_buttons("Отмена", Gtk.ResponseType.CANCEL, "Восстановить", Gtk.ResponseType.OK)
        area = dlg.get_content_area()
        area.set_spacing(8)
        area.set_margin_start(12)
        area.set_margin_end(12)
        area.pack_start(Gtk.Label(
            label="Текущие сохранения будут перезаписаны. Игра должна быть закрыта.",
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
            self._run(["restore", appid, chosen], f"Восстановление: {name}", buttons)

    def clear_shaders(self, appid, name, buttons):
        if confirm(self.window, f"Очистить шейдер-кэш «{name}»?",
                   "Кэш соберётся заново при следующем запуске, первые минуты игра может подтормаживать."):
            self._run(["clear-shaders", appid], f"Очистка шейдеров: {name}", buttons)

    def reset_prefix(self, appid, name, buttons):
        if confirm(self.window, f"Сбросить данные «{name}»?",
                   "Удаляется префикс Proton или данные Android-приложения. Перед удалением "
                   "будет сделан бэкап сохранений. Настройки игры и установленные в префикс "
                   "библиотеки пропадут, Steam создаст всё заново при запуске."):
            self._run(["reset-prefix", appid], f"Сброс префикса: {name}", buttons)


# ---------- decky plugins tab ----------

class PluginsPage:
    """Installed Decky plugins: enable/disable, update from store, remove."""

    def __init__(self, runner, window):
        self.runner = runner
        self.window = window
        self.script = tool("decky_plugins.py")
        self.widget, self.box = page()

        top = row_box()
        text, self.summary = title_block("Плагины Decky")
        self.summary.set_text("~/homebrew/plugins")
        top.pack_start(text, True, True, 0)
        for label, handler in (
            ("Обновить список", lambda _b: self.refresh()),
            ("Магазин в шлеме", lambda b: self.open_in_headset(b, "store")),
            ("Панель в шлеме", lambda b: self.open_in_headset(b, "panel")),
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
                        "Открытие Decky в шлеме", widgets=[btn])

    def refresh(self):
        self.summary.set_text("Загрузка списка и проверка обновлений…")

        def done(res):
            for child in self.list.get_children():
                child.destroy()
            plugins = parse_tsv(res.stdout, 5)
            updates = sum(1 for p in plugins if p[4])
            self.summary.set_text(f"Установлено: {len(plugins)}  ·  обновлений: {updates}")
            if not plugins:
                self.list.pack_start(section("Плагины не установлены"), False, False, 0)
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
        state = "отключён" if disabled else "включён"
        update = f"  ·  доступно обновление: {latest}" if latest else ""
        sub.set_text(f"версия {version}  ·  {state}{update}")
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
            add("Включить", ["enable", folder], f"Включение {name}")
        else:
            add("Отключить", ["disable", folder], f"Отключение {name}")
        add("Обновить", ["update", folder], f"Обновление {name}", sensitive=bool(latest))
        add("Удалить", ["remove", folder], f"Удаление {name}", danger=True,
            question=(f"Удалить плагин «{name}»?",
                      "Папка плагина будет удалена. Decky перезапустится."))
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
        super().__init__(title=f"Лог: {title}")
        self.path = path
        self.set_transient_for(parent)
        self.set_default_size(1000, 640)

        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        headerbar.set_title(f"Лог: {title}")
        headerbar.set_subtitle(path)
        self.set_titlebar(headerbar)
        btn_reload = Gtk.Button(label="Обновить")
        btn_reload.connect("clicked", lambda _b: self.load())
        headerbar.pack_start(btn_reload)
        btn_dir = Gtk.Button(label="Папка логов")
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
                text = f"… показаны последние {self.MAX_BYTES // 1024 // 1024} МБ из " \
                       f"{size // 1024 // 1024} МБ …\n" + text
        except OSError as e:
            text = f"Не удалось прочитать {self.path}: {e}"
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

        self.box.pack_start(section("Установить APK"), False, False, 0)
        form = row_box()
        form.set_orientation(Gtk.Orientation.VERTICAL)
        form.set_spacing(8)

        name_row = Gtk.Box(spacing=8)
        name_row.pack_start(Gtk.Label(label="Название в библиотеке:", xalign=0), False, False, 0)
        self.name = Gtk.Entry()
        self.name.set_placeholder_text("например, Моя игра")
        name_row.pack_start(self.name, True, True, 0)
        form.pack_start(name_row, False, False, 0)

        apk_row = Gtk.Box(spacing=8)
        self.apk_label = Gtk.Label(label="APK не выбран", xalign=0)
        self.apk_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.apk_label.get_style_context().add_class("tool-sub")
        btn_apk = Gtk.Button(label="Выбрать APK…")
        btn_apk.connect("clicked", self.choose_apk)
        apk_row.pack_start(btn_apk, False, False, 0)
        apk_row.pack_start(self.apk_label, True, True, 0)
        form.pack_start(apk_row, False, False, 0)

        obb_row = Gtk.Box(spacing=8)
        self.obb_label = Gtk.Label(label="OBB нет (необязательно)", xalign=0)
        self.obb_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.obb_label.get_style_context().add_class("tool-sub")
        btn_obb = Gtk.Button(label="Выбрать OBB…")
        btn_obb.connect("clicked", self.choose_obbs)
        obb_row.pack_start(btn_obb, False, False, 0)
        obb_row.pack_start(self.obb_label, True, True, 0)
        form.pack_start(obb_row, False, False, 0)

        lepton_row = Gtk.Box(spacing=8)
        lepton_row.pack_start(Gtk.Label(label="Среда Android:", xalign=0), False, False, 0)
        self.lepton = Gtk.ComboBoxText()
        self.lepton.append("auto", "Авто (по minSdk из APK)")
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
            label="Приложение появится в библиотеке Steam и запустится через Lepton. "
                  "Steam перезапустится.", xalign=0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("tool-sub")
        action_row.pack_start(hint, True, True, 0)
        self.btn_install = Gtk.Button(label="Установить")
        self.btn_install.connect("clicked", self.install)
        action_row.pack_start(self.btn_install, False, False, 0)
        form.pack_start(action_row, False, False, 0)
        self.box.pack_start(form, False, False, 0)

        self.box.pack_start(section("Установленные"), False, False, 0)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.list, False, False, 0)
        self.refresh()

    def _chooser(self, title, pattern, multiple):
        dlg = Gtk.FileChooserDialog(title=title, transient_for=self.window,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Отмена", Gtk.ResponseType.CANCEL, "Выбрать", Gtk.ResponseType.OK)
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
        files = self._chooser("Выберите APK", "*.apk", False)
        if files:
            self.apk = files[0]
            self.apk_label.set_text(self.apk)
            if not self.name.get_text().strip():
                self.name.set_text(os.path.splitext(os.path.basename(self.apk))[0])
            self.show_apk_info()

    def show_apk_info(self):
        self.apk_info.set_text("Чтение APK…")
        apk = self.apk

        def done(res):
            info = parse_kv(res.stdout)
            if res.returncode != 0 or not info.get("min_sdk"):
                self.apk_info.set_text("Не удалось прочитать APK")
                return False
            env = "Lepton 14" if info.get("lepton") == "14" else "Lepton (Android 11)"
            self.apk_info.set_text(f"{info.get('app_id', '?')}  ·  minSdk {info['min_sdk']}  ·  "
                                   f"авто: {env}")
            return False

        threading.Thread(
            target=lambda: GLib.idle_add(done, run_user([self.script, "info", apk])),
            daemon=True,
        ).start()

    def choose_obbs(self, _btn):
        self.obbs = self._chooser("Выберите OBB (можно несколько)", "*.obb", True)
        self.obb_label.set_text(", ".join(os.path.basename(f) for f in self.obbs)
                                if self.obbs else "OBB нет (необязательно)")

    def install(self, _btn):
        name = self.name.get_text().strip()
        if not name or not self.apk:
            self.runner.log("Укажи название и выбери APK")
            return
        if "/" in name:
            self.runner.log("Название не должно содержать «/»")
            return
        if not confirm(self.window, f"Установить «{name}»?",
                       "Steam перезапустится, в шлеме это займёт около полуминуты."):
            return
        args = ([self.script, "install", name, self.apk] + self.obbs
                + ["--lepton", self.lepton.get_active_id() or "auto"])
        self.runner.run(run_user, args, f"Установка {name}",
                        on_done=lambda _r: self.refresh(), widgets=[self.btn_install])

    def refresh(self):
        def done(res):
            for child in self.list.get_children():
                child.destroy()
            apps = parse_tsv(res.stdout, 8)
            if not apps:
                self.list.pack_start(section("Пока ничего не установлено"), False, False, 0)
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
        state = "запускался" if has_container else "ещё не запускался"
        env = {"lepton": "Lepton (Android 11)", "lepton_14": "Lepton 14"}.get(tool_name, tool_name)
        folder = os.path.dirname(apk)
        sub.set_text(f"{env}  ·  {size} МБ  ·  OBB: {obbs}  ·  {state}  ·  {folder}")
        box.pack_start(text, True, True, 0)

        btn_log = Gtk.Button(label="Лог")
        btn_log.set_sensitive(bool(log))
        btn_log.set_tooltip_text(log or "Лога пока нет: приложение ещё не запускалось")
        btn_log.connect("clicked", lambda _b: LogViewer(self.window, name, log, self.open_path))
        box.pack_start(btn_log, False, False, 0)

        btn_dir = Gtk.Button(label="Папка")
        btn_dir.set_tooltip_text(folder)
        btn_dir.connect("clicked", lambda _b: self.open_path(folder))
        box.pack_start(btn_dir, False, False, 0)

        btn = Gtk.Button(label="Удалить")
        btn.get_style_context().add_class("danger")
        btn.connect("clicked", lambda _b: self.remove(name, btn))
        box.pack_start(btn, False, False, 0)
        return box

    def open_path(self, path):
        """Opens a file or folder in the default desktop app (Kate, Dolphin, ...)."""
        if not path or not os.path.exists(path):
            self.runner.log(f"Не найдено: {path}")
            return
        try:
            subprocess.Popen(["xdg-open", path], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.runner.log(f"Открыто: {path}")
        except OSError as e:
            self.runner.log(f"Не удалось открыть {path}: {e}")

    def remove(self, name, btn):
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.NONE,
                                text=f"Удалить «{name}» из библиотеки?")
        dlg.format_secondary_text(
            "Контейнер Lepton с сохранениями останется. Steam перезапустится.")
        dlg.add_buttons("Отмена", Gtk.ResponseType.CANCEL,
                        "Только ярлык", 1, "Ярлык и файлы", 2)
        resp = dlg.run()
        dlg.destroy()
        if resp not in (1, 2):
            return
        args = [self.script, "remove", name] + (["--purge"] if resp == 2 else [])
        self.runner.run(run_user, args, f"Удаление {name}",
                        on_done=lambda _r: self.refresh(), widgets=[btn])


# ---------- transfer to PC tab ----------

def human_size(n):
    for unit, step in (("ГБ", 1 << 30), ("МБ", 1 << 20), ("КБ", 1 << 10)):
        if n >= step:
            return f"{n / step:.1f} {unit}"
    return f"{n} Б"


class TransferPage:
    """Files/folders from the Frame to the PC: queued here, pulled by the PC agent."""

    def __init__(self, runner, window):
        self.runner = runner
        self.window = window
        self.script = tool("to_pc.py")
        self.widget, self.box = page()

        top = row_box()
        text, self.agent = title_block("Отправить на ПК (Загрузки\\SteamFrame)")
        top.pack_start(text, True, True, 0)
        for label, handler in (("Файлы…", self.pick_files), ("Папка…", self.pick_folder)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", handler)
            top.pack_start(btn, False, False, 0)
        self.box.pack_start(top, False, False, 0)

        hint = Gtk.Label(
            label="Агент на ПК забирает очередь каждые 5 секунд. Если ПК выключен, "
                  "файлы подождут в очереди. Большие файлы не занимают лишнего места: "
                  "в очередь кладутся жёсткие ссылки.", xalign=0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("tool-sub")
        hint.set_margin_start(16)
        hint.set_margin_end(16)
        self.box.pack_start(hint, False, False, 0)

        head = Gtk.Box(spacing=8)
        head.pack_start(section("Очередь"), True, True, 0)
        btn_clear = Gtk.Button(label="Очистить очередь")
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
        dlg.add_buttons("Отмена", Gtk.ResponseType.CANCEL, "Отправить", Gtk.ResponseType.OK)
        dlg.set_select_multiple(True)
        dlg.set_current_folder(os.path.expanduser("~"))
        paths = dlg.get_filenames() if dlg.run() == Gtk.ResponseType.OK else []
        dlg.destroy()
        if paths:
            self.runner.run(run_user, [self.script, "add"] + paths,
                            f"В очередь на ПК: {len(paths)}", on_done=lambda _r: self.refresh())

    def pick_files(self, _btn):
        self.pick("Файлы для отправки на ПК", Gtk.FileChooserAction.OPEN)

    def pick_folder(self, _btn):
        self.pick("Папки для отправки на ПК", Gtk.FileChooserAction.SELECT_FOLDER)

    def clear(self, _btn):
        if confirm(self.window, "Очистить очередь?",
                   "Файлы, которые ещё не ушли на ПК, будут убраны из очереди. "
                   "Оригиналы на Frame не пострадают."):
            self.runner.run(run_user, [self.script, "clear"], "Очистка очереди",
                            on_done=lambda _r: self.refresh())

    def refresh(self):
        def done(listing, status):
            age = int(status.stdout.strip() or -1)
            if age < 0:
                self.agent.set_text("Агент на ПК ещё не подключался")
            elif age < 30:
                self.agent.set_text(f"ПК на связи ({age} с назад)")
            else:
                self.agent.set_text(f"ПК не на связи {age // 60} мин — включён ли ПК и агент?")
            for child in self.queue.get_children():
                child.destroy()
            items = parse_tsv(listing.stdout, 2)
            if not items:
                self.queue.pack_start(section("Пусто — всё доставлено"), False, False, 0)
            for name, size in items:
                box = row_box()
                t, sub = title_block(name)
                sub.set_text(f"{human_size(int(size))}  ·  ждёт, пока ПК заберёт")
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
        self.entry.set_placeholder_text("Поиск на Flathub: telegram, firefox, vlc…")
        self.entry.connect("activate", lambda _e: self.search())
        top.pack_start(self.entry, True, True, 0)
        self.btn_search = Gtk.Button(label="Найти")
        self.btn_search.connect("clicked", lambda _b: self.search())
        top.pack_start(self.btn_search, False, False, 0)
        fix = Gtk.Button(label="Починить Flathub")
        fix.connect("clicked", self.fix_flathub)
        top.pack_start(fix, False, False, 0)
        self.box.pack_start(top, False, False, 0)

        self.box.pack_start(section("Результаты поиска"), False, False, 0)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.pack_start(self.results, False, False, 0)

        self.box.pack_start(section("Установлено"), False, False, 0)
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
            btn = Gtk.Button(label="Удалить")
            btn.connect("clicked", lambda _b: self.remove(app_id, name, btn))
        else:
            btn = Gtk.Button(label="Установить")
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
                self.installed.pack_start(section("Ничего не установлено"), False, False, 0)
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
                self.results.pack_start(section("Ничего не найдено"), False, False, 0)
            self.results.show_all()

        self.runner.run(run_user, [self.script, "search", query], f"Поиск «{query}»",
                        on_done=done, widgets=[self.btn_search])

    def install(self, app_id, name, btn):
        def done(_res):
            self.refresh_installed()
            self.search()

        self.runner.run(run_root, [self.script, "install", app_id], f"Установка {name}",
                        on_done=done, widgets=[btn])

    def remove(self, app_id, name, btn):
        if not confirm(self.window, f"Удалить {name}?", "Данные приложения в ~/.var/app останутся."):
            return
        self.runner.run(run_root, [self.script, "remove", app_id], f"Удаление {name}",
                        on_done=lambda _r: self.refresh_installed(), widgets=[btn])

    def fix_flathub(self, btn):
        self.runner.run(run_root, [self.script, "fix-flathub"], "Починка Flathub",
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
        headerbar.set_subtitle(f"версия {VERSION}")
        self.set_titlebar(headerbar)

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
        tools.pack_start(section("Сеть"), False, False, 0)
        # AmneziaVPN is not part of the public release; the row appears only where its
        # scripts were added by hand (tools/amneziavpn.sh).
        if os.path.exists(tool("amneziavpn.sh")):
            tools.pack_start(StatusTool(runner, "AmneziaVPN (нативная сборка ARM64)", "amneziavpn.sh",
                                        install_label="Установить / обновить",
                                        reinstall=True, repair=True),
                             False, False, 0)
        tools.pack_start(RegionTool(runner), False, False, 0)
        tools.pack_start(StatusTool(runner, "Wi-Fi без энергосбережения", "wifi.sh",
                                    install_label="Выключить", remove_label="Включить"),
                         False, False, 0)
        tools.pack_start(VrHudTool(runner), False, False, 0)
        tools.pack_start(section("Плагины"), False, False, 0)
        tools.pack_start(DeckyTool(runner), False, False, 0)
        tools.pack_start(section("Система"), False, False, 0)
        tools.pack_start(StatusTool(runner, "Запись в системный раздел", "readonly.sh",
                                    install_label="Разблокировать",
                                    remove_label="Заблокировать",
                                    status_as_root=True),
                         False, False, 0)
        tools.pack_start(StatusTool(runner, "RDP: Wi-Fi без запроса пароля", "rdp_wifi_scan.sh",
                                    install_label="Включить", remove_label="Выключить",
                                    status_as_root=True),
                         False, False, 0)
        tools.pack_start(QuickActions(runner, self), False, False, 0)
        tools.pack_start(section("Скриншоты"), False, False, 0)
        tools.pack_start(StatusTool(runner, "Копировать скриншоты на Frame (Pictures/Screenshots)",
                                    "screenshots_local.sh", install_label="Включить",
                                    remove_label="Выключить", actions_as_root=False),
                         False, False, 0)
        tools.pack_start(StatusTool(runner, "Копировать скриншоты на ПК (Изображения\\SteamFrame)",
                                    "screenshots_pc.sh", install_label="Включить",
                                    remove_label="Выключить", actions_as_root=False),
                         False, False, 0)
        notebook.append_page(tools_page, Gtk.Label(label="Инструменты"))

        notebook.append_page(PluginsPage(runner, self).widget, Gtk.Label(label="Плагины"))
        notebook.append_page(GamesPage(runner, self).widget, Gtk.Label(label="Игры"))
        notebook.append_page(AppsPage(runner, self).widget, Gtk.Label(label="Приложения"))
        notebook.append_page(AndroidPage(runner, self).widget, Gtk.Label(label="Android"))
        notebook.append_page(TransferPage(runner, self).widget, Gtk.Label(label="Передача"))

        dev_page, dev = page()
        dev.pack_start(section("Просмотр"), False, False, 0)
        dev.pack_start(UiStreamTool(runner), False, False, 0)
        notebook.append_page(dev_page, Gtk.Label(label="Разработка"))

    def log(self, text):
        self.status.set_text(text)


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
