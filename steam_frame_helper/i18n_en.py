"""English UI strings for Steam Frame Helper (see i18n.py).

Keys are the exact Russian source strings used in the code; terms follow docs/GLOSSARY.md.
"""

EN = {
    # Wi-Fi regions
    "Германия": "Germany",
    "Польша": "Poland",
    "Финляндия": "Finland",
    "Нидерланды": "Netherlands",
    "Франция": "France",
    "Великобритания": "United Kingdom",
    "США": "USA",
    "Россия": "Russia",

    # status line / runner
    "Нет прав root (sudo/pkexec)": "No root access (sudo/pkexec)",
    "код {code}": "code {code}",
    "{message} — готово": "{message} — done",
    "{message} — ошибка: {error}": "{message} — error: {error}",

    # common buttons
    "Установить": "Install",
    "Удалить": "Remove",
    "Починить": "Repair",
    "Включить": "Turn on",
    "Выключить": "Turn off",
    "Отключить": "Turn off",
    "Установить / обновить": "Install / update",
    "Показать / скрыть": "Show / hide",
    "показать / скрыть": "show / hide",
    "Отмена": "Cancel",
    "Выбрать": "Choose",
    "Отправить": "Send",
    "Обновить": "Refresh",
    "Обновить список": "Refresh list",
    "Найти": "Search",
    "Лог": "Log",
    "Папка": "Folder",
    "Папка…": "Folder…",
    "Файлы…": "Files…",
    "Открыть в шлеме": "Open in headset",
    "Копировать ссылку": "Copy link",
    "Скопировано: {url}": "Copied: {url}",

    # tools tab
    "Сеть": "Network",
    "Система": "System",
    "Статистика соединения с ПК (в шлеме)": "PC connection stats (in headset)",
    "AmneziaVPN (нативная сборка ARM64)": "AmneziaVPN (native ARM64 build)",
    "Поменять регион Wi-Fi": "Change Wi-Fi region",
    "Wi-Fi без энергосбережения": "Wi-Fi without power saving",
    "Запись в системный раздел": "System partition write access",
    "Разблокировать": "Unlock",
    "Заблокировать": "Lock",
    "Быстрые действия": "Quick actions",
    "Перезапуск Steam, перезагрузка": "Restart Steam, reboot",
    "Перезапустить Steam": "Restart Steam",
    "Перезагрузить": "Reboot",
    "Перезагрузить Steam Frame?": "Reboot Steam Frame?",

    # plugins tab
    "Decky Loader (ARM64, экспериментально)": "Decky Loader (ARM64, experimental)",
    "Открытие панели Decky в шлеме": "Opening the Decky panel in the headset",
    "Открытие Decky в шлеме": "Opening Decky in the headset",
    "Где показывать Decky в шлеме": "Where to show Decky in the headset",
    "Левое меню": "Left menu",
    "Быстрые настройки": "Quick Settings",
    "Меню в шлеме обновится при следующем открытии":
        "The headset menu will update the next time it opens",
    "Нужен запущенный Steam и плагин SFH Frame Menu в Decky":
        "Steam must be running and the SFH Frame Menu plugin must be installed in Decky",
    "Decky должен остаться хотя бы в одном месте": "Decky must stay in at least one place",
    "Decky в шлеме: место показа": "Decky in the headset: where to show",
    "Установленные плагины": "Installed plugins",
    "Плагины Decky": "Decky plugins",
    "Магазин в шлеме": "Store in headset",
    "Панель в шлеме": "Panel in headset",
    "Загрузка списка и проверка обновлений…": "Loading the list and checking for updates…",
    "Установлено: {n}  ·  обновлений: {u}": "Installed: {n}  ·  updates: {u}",
    "Плагины не установлены": "No plugins installed",
    "включён": "turned on",
    "отключён": "turned off",
    "  ·  доступно обновление: {latest}": "  ·  update available: {latest}",
    "версия {version}  ·  {state}{update}": "version {version}  ·  {state}{update}",
    "Включение {name}": "Turning on {name}",
    "Отключение {name}": "Turning off {name}",
    "Обновление {name}": "Updating {name}",
    "Удаление {name}": "Removing {name}",
    "Удалить плагин «{name}»?": "Remove the plugin “{name}”?",
    "Папка плагина будет удалена. Decky перезапустится.":
        "The plugin folder will be deleted. Decky will restart.",

    # games tab
    "Игры Steam": "Steam games",
    "Бэкапы сохранений: ~/steam_frame_helper_backups":
        "Save backups: ~/steam_frame_helper_backups",
    "Игры не найдены": "No games found",
    "AppID {appid}  ·  {kind}  ·  шейдеры: {shader}  ·  бэкапов: {backups}":
        "AppID {appid}  ·  {kind}  ·  shaders: {shader}  ·  backups: {backups}",
    "Бэкап": "Back up",
    "Восстановить": "Restore",
    "Очистить шейдеры": "Clear shaders",
    "Сбросить префикс": "Reset prefix",
    "Бэкап сохранений: {name}": "Backing up saves: {name}",
    "Восстановить: {name}": "Restore: {name}",
    "Текущие сохранения будут перезаписаны. Игра должна быть закрыта.":
        "Current saves will be overwritten. The game must be closed.",
    "Восстановление: {name}": "Restoring: {name}",
    "Очистить шейдер-кэш «{name}»?": "Clear the shader cache for “{name}”?",
    "Кэш соберётся заново при следующем запуске, первые минуты игра может подтормаживать.":
        "The cache will be rebuilt on the next launch, so the game may stutter for the first few minutes.",
    "Очистка шейдеров: {name}": "Clearing shaders: {name}",
    "Сбросить данные «{name}»?": "Reset data for “{name}”?",
    "Удаляется префикс Proton или данные Android-приложения. Перед удалением будет сделан бэкап сохранений. Настройки игры и установленные в префикс библиотеки пропадут, Steam создаст всё заново при запуске.":
        "The Proton prefix or the Android app data will be deleted. Your saves are backed up first. Game settings and libraries installed into the prefix will be lost; Steam recreates everything on launch.",
    "Сброс префикса: {name}": "Resetting prefix: {name}",

    # log viewer
    "Лог: {title}": "Log: {title}",
    "Папка логов": "Logs folder",
    "… показаны последние {shown} МБ из {total} МБ …": "… showing the last {shown} MB of {total} MB …",
    "Не удалось прочитать {path}: {error}": "Couldn't read {path}: {error}",

    # apps tab (Android)
    "Установить APK": "Install APK",
    "Название в библиотеке:": "Library name:",
    "например, Моя игра": "e.g. My game",
    "APK не выбран": "No APK selected",
    "Выбрать APK…": "Choose APK…",
    "OBB нет (необязательно)": "No OBB (optional)",
    "Выбрать OBB…": "Choose OBB…",
    "Среда Android:": "Android environment:",
    "Авто (по minSdk из APK)": "Auto (by minSdk from the APK)",
    "Приложение появится в библиотеке Steam и запустится через Lepton. Steam перезапустится.":
        "The app will appear in your Steam library and run through Lepton. Steam will restart.",
    "Установленные": "Installed",
    "Выберите APK": "Choose an APK",
    "Выберите OBB (можно несколько)": "Choose OBB files (you can pick several)",
    "Чтение APK…": "Reading APK…",
    "Не удалось прочитать APK": "Couldn't read the APK",
    "{app_id}  ·  minSdk {min_sdk}  ·  авто: {env}": "{app_id}  ·  minSdk {min_sdk}  ·  auto: {env}",
    "Укажи название и выбери APK": "Enter a name and choose an APK",
    "Название не должно содержать «/»": "The name must not contain “/”",
    "Установить «{name}»?": "Install “{name}”?",
    "Steam перезапустится, в шлеме это займёт около полуминуты.":
        "Steam will restart; in the headset this takes about 30 seconds.",
    "Установка {name}": "Installing {name}",
    "Пока ничего не установлено": "Nothing installed yet",
    "запускался": "has been launched",
    "ещё не запускался": "not launched yet",
    "{env}  ·  {size} МБ  ·  OBB: {obbs}  ·  {state}  ·  {folder}":
        "{env}  ·  {size} MB  ·  OBB: {obbs}  ·  {state}  ·  {folder}",
    "Лога пока нет: приложение ещё не запускалось": "No log yet: the app hasn't been launched",
    "Не найдено: {path}": "Not found: {path}",
    "Открыто: {path}": "Opened: {path}",
    "Не удалось открыть {path}: {error}": "Couldn't open {path}: {error}",
    "Удалить «{name}» из библиотеки?": "Remove “{name}” from the library?",
    "Контейнер Lepton с сохранениями останется. Steam перезапустится.":
        "The Lepton container with saves will stay. Steam will restart.",
    "Только ярлык": "Shortcut only",
    "Ярлык и файлы": "Shortcut and files",

    # transfer tab
    "ГБ": "GB",
    "МБ": "MB",
    "КБ": "KB",
    "Б": "B",
    "Скриншоты": "Screenshots",
    "Копировать скриншоты на Frame (Pictures/Screenshots)":
        "Copy screenshots to Frame (Pictures/Screenshots)",
    "Копировать скриншоты на ПК (Изображения\\SteamFrame)":
        "Copy screenshots to PC (Pictures\\SteamFrame)",
    "Файлы на ПК": "Files to PC",
    "Отправить на ПК (Загрузки\\SteamFrame)": "Send to PC (Downloads\\SteamFrame)",
    "Агент на ПК забирает очередь каждые 5 секунд. Если ПК выключен, файлы подождут в очереди. Большие файлы не занимают лишнего места: в очередь кладутся жёсткие ссылки.":
        "The PC agent picks up the queue every 5 seconds. If the PC is off, files wait in the queue. Large files take no extra space: the queue holds hard links.",
    "Очередь": "Queue",
    "Очистить очередь": "Clear queue",
    "В очередь на ПК: {n}": "Queued for PC: {n}",
    "Файлы для отправки на ПК": "Files to send to PC",
    "Папки для отправки на ПК": "Folders to send to PC",
    "Очистить очередь?": "Clear the queue?",
    "Файлы, которые ещё не ушли на ПК, будут убраны из очереди. Оригиналы на Frame не пострадают.":
        "Files not yet sent to the PC will be removed from the queue. The originals on Frame are not touched.",
    "Очистка очереди": "Clearing queue",
    "Агент на ПК ещё не подключался": "The PC agent hasn't connected yet",
    "ПК на связи ({age} с назад)": "PC online ({age} s ago)",
    "ПК не на связи {min} мин — включён ли ПК и агент?":
        "PC offline for {min} min — are the PC and the agent running?",
    "Пусто — всё доставлено": "Empty — everything delivered",
    "{size}  ·  ждёт, пока ПК заберёт": "{size}  ·  waiting for the PC to pick it up",

    # apps tab (Flatpak)
    "Поиск на Flathub: telegram, firefox, vlc…": "Search Flathub: telegram, firefox, vlc…",
    "Починить Flathub": "Repair Flathub",
    "Результаты поиска": "Search results",
    "Установлено": "Installed",
    "Ничего не установлено": "Nothing installed",
    "Ничего не найдено": "Nothing found",
    "Поиск «{query}»": "Searching “{query}”",
    "Удалить {name}?": "Remove {name}?",
    "Данные приложения в ~/.var/app останутся.": "App data in ~/.var/app will stay.",
    "Починка Flathub": "Repairing Flathub",

    # main window
    "версия {version}": "version {version}",
    "Инструменты": "Tools",
    "Плагины": "Plugins",
    "Игры": "Games",
    "Приложения": "Apps",
    "Передача": "Transfer",
    "Просмотр": "Viewing",
    "Удалённый доступ": "Remote access",
    "Интерфейс Steam в браузере на ПК": "Steam UI in a PC browser",
    "RDP: Wi-Fi без запроса пароля": "RDP: Wi-Fi without a password prompt",
    "Разработка": "Developer",
}
