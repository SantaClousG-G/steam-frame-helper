# Steam Frame Helper: user guide

English | [Русский](GUIDE.ru.md)

Steam Frame Helper (SFH) is a window of tweaks and utilities for the Steam Frame. It runs in SteamOS Desktop Mode. Almost every feature is turned on and off with a single button, and this guide tells you what each one actually changes on the system.

This guide matches Steam Frame Helper 1.7.2.

## Contents

1. [Requirements](#requirements)
2. [Installation (Frame)](#installation-frame)
3. [First launch](#first-launch)
4. [Tools tab](#tools-tab)
5. [Plugins tab](#plugins-tab)
6. [Games tab](#games-tab)
7. [Apps tab](#apps-tab)
8. [Android tab](#android-tab)
9. [Transfer tab](#transfer-tab)
10. [Developer tab](#developer-tab)
11. [Decky quick menu (SFH Frame Menu)](#decky-quick-menu-sfh-frame-menu)
12. [PC part](#pc-part)
13. [Updating and uninstalling](#updating-and-uninstalling)
14. [Troubleshooting and FAQ](#troubleshooting-and-faq)
15. [Safety notes](#safety-notes)

## Requirements

- A Steam Frame running SteamOS (aarch64). On other hardware the app starts, but some features will not work.
- Access to Desktop Mode on the Frame.
- Internet access on the Frame for installation, Decky and Flathub apps.
- A password for the SteamOS user `steamos`. There is none by default, so you need to set one once (see below).
- For the PC part: Windows 10 or 11 with the OpenSSH client (built into Windows as the "OpenSSH Client" optional feature), and the PC and the Frame on the same network.

### The `steamos` user password

The `steamos` user has no password by default. Actions that change the system (Wi-Fi region, Decky, unlocking the system partition, reboot, installing Flatpak apps) need root. The app first tries `sudo` without a password, then opens a system password dialog (`pkexec`). Without a password neither works, and the status line shows "No root access (sudo/pkexec)".

Set a password once. Open Konsole and run:

```bash
passwd
```

You will also need this password for SSH from the PC.

To make SSH available on the Frame, turn the service on (once):

```bash
sudo systemctl enable --now sshd
```

## Installation (Frame)

1. On the Frame, switch to Desktop Mode.
2. Open Konsole (or log in to the Frame over SSH).
3. Run:

```bash
curl -fsSL https://raw.githubusercontent.com/SantaClousG-G/steam-frame-helper/main/install.sh | bash
```

The installer downloads the latest release, copies the app to `~/.config/steam_frame_helper` and adds **Steam Frame Helper** to the application menu. Run it as a regular user, not with `sudo`. It does not change any system settings.

To start the app, open the application menu and choose **Steam Frame Helper**.

## First launch

The window has four parts.

| Element | What it does |
|---|---|
| Window header | Shows "Steam Frame Helper" and the version number. On the right: the language switcher and the minimize, maximize and close buttons. |
| Language switcher | Choose "Русский" or "English". When you change it, the app restarts itself in the new language and remembers the choice. The connection stats service also restarts so it switches language too. If you have never picked a language, the app uses the Steam client language, then the system language. |
| Tabs | Tools, Plugins, Games, Apps, Android, Transfer, Developer. |
| Status line | The bottom line of the window. It shows what the app is doing right now ("… — done" or "… — error: reason"). If the text is cut off, hover over it to see the full text in a tooltip. |

How the rows work:

- On the left there is a status mark: a green check means "on / installed", a red cross means "off / not installed".
- Under the title, grey text shows the current state (version, address, what is on right now). Long lines show their full text in a tooltip.
- Buttons are on the right. Buttons that make no sense right now are greyed out (for example, you cannot "Remove" something that is not there).
- While an action runs, the row's buttons are disabled and the result is written to the status line.
- Risky actions (reboot, removal, data reset) ask for confirmation.

Sections inside tabs collapse: click a section heading (for example, "NETWORK"). The app remembers which sections are collapsed and opens the window the same way next time.

## Tools tab

Two sections: Network and System.

### Network section

#### Change Wi-Fi region

Shows the current Wi-Fi region ("Set: XX · Wi-Fi currently uses: YY"). The region defines the allowed channels and transmit power.

| Element | What happens |
|---|---|
| Region list | DE — Germany, PL — Poland, FI — Finland, NL — Netherlands, FR — France, GB — United Kingdom, US — USA, RU — Russia. |
| Install | Writes the chosen region to the system settings file and applies it immediately. The region is kept after a reboot. The original settings file is backed up once. |
| Remove | Disables the saved region and returns to the generic region "00". |

Needs root. Do not pick RU on the Steam Frame: with it the Steam wireless adapter (SoftAP) stops working, so the app asks for confirmation before setting RU. If you picked it by mistake, press "Remove" or install a different region.

#### Wi-Fi without power saving

Controls Wi-Fi power saving on the Frame. A green check means power saving is off. Turning it off lowers streaming latency but uses a little more battery.

| Button | What happens |
|---|---|
| Turn off | Turns Wi-Fi power saving off (immediately and permanently: the setting that turned it on is removed). |
| Turn on | Turns Wi-Fi power saving on and adds a system setting so it stays on after a reboot. |

Needs root. Valve ships the Frame with power saving already off, so you need this only if you or another program turned it on.

#### PC connection stats (in headset)

Turns on a small window that floats at the bottom centre of your view in the headset and updates 4 times a second. It shows:

- **STREAM**: stream quality and total speed;
- for each link (**ADAPTER** is the Steam wireless adapter, **WI-FI** is your home Wi-Fi / router): channel and channel width, signal level (dBm), ping and packet loss as measured by Steam itself, traffic (Mbit/s up and down) and the PHY rate of the link;
- battery level and the current time.

Steam's "ping" is the worst round-trip time of the last second, which is what you feel as a stutter. If no stream is running, the window says so ("not running"); if a link is not used, it says "not used in stream".

| Button | What happens |
|---|---|
| Show / hide | Shows or hides the window in the headset. Available when the stats are turned on. |
| Turn on | Creates and starts the user service `sfh-vr-hud`, which starts at every login. The window is hidden at first: open it with the Show / hide button or from the Decky menu. The service connects to SteamVR only after Steam has fully started it (about 20 seconds) and never starts SteamVR itself. No root needed. |
| Turn off | Stops the service and removes the autostart. |

You can also toggle it from inside the headset, in the Decky quick menu: the SFH Frame Menu plugin, "Connection stats" section, "Show in headset" switch (see [Decky quick menu](#decky-quick-menu-sfh-frame-menu)). Toggling it by clicking the thumbsticks is not possible: SteamVR does not deliver controller input to background overlays.

### System section

#### System partition write access

The SteamOS root partition is read-only by default. This feature removes and restores that protection (`steamos-readonly`). A green check means the partition is writable.

| Button | What happens |
|---|---|
| Unlock | Allows writing to the system partition. Use it only if you know why (for example, some tweaks need it). |
| Lock | Restores the protection: the partition is read-only again. |

Needs root. Lock the partition again when you are done. SteamOS updates may reset changes made on the system partition.

#### Quick actions

| Button | What happens |
|---|---|
| Stop streaming | Ends PC streaming by stopping the Frame's streaming client (`vrlink`). Asks "Stop streaming from the PC?" first. Works even when the headset's "Stop streaming" button no longer responds. |
| Restart Steam | Restarts the Steam client (the user service `steam.service`). A running game or VR session closes and the Steam UI reloads. There is no confirmation. |
| Reboot | Reboots the Frame. Asks "Reboot Steam Frame?" first. Needs root. |

## Plugins tab

Two sections: Decky Loader and Installed plugins.

### Decky Loader section

Decky Loader loads plugins into Steam. On the Frame the official ARM64 build is used. It is marked experimental.

#### Decky Loader (ARM64, experimental)

The subtitle shows the Decky version, the service state, whether port 1337 is reachable, the plugin store and the number of installed plugins.

| Button | What happens |
|---|---|
| Open in headset | Opens the Decky panel in the headset, on a page of the Steam UI. Steam must be running. This is a fallback: the left menu or Quick Settings is more convenient (see below). |
| Install / update | Downloads the latest stable Decky from GitHub and verifies its SHA-256 checksum (a mismatch cancels the install). Creates the `~/homebrew` folder and the `plugin_loader` system service and starts it. Enables the Steam UI debugging port that Decky needs. Installs the bundled SFH Frame Menu plugin. The plugin store stays the official one. Adds a "Decky" shortcut to the Steam library (Steam restarts for a few seconds to do this). Pressing it again updates Decky to the latest version. |
| Repair | Does not download Decky again. It stops the service, checks folders and permissions, restores the service file, the bundled plugin and the library shortcut, then restarts the service. If the Decky file is missing, it reinstalls Decky. Steam restarts as well. |
| Remove | Removes the Decky service and loader, and the "Decky" library shortcut. Installed plugins in `~/homebrew/plugins` are kept. |

All buttons except "Open in headset" need root.

#### Third-party plugin store

By default Decky uses its official plugin store. Here you can connect a third-party store (for example, SteamDeckBase) or go back to the official one.

| Control | What happens |
|---|---|
| List with an input field | Store addresses: SteamDeckBase, stores you connected before, and the current one. Pick one from the list or type your own address (starts with `https://`). |
| Connect | Asks for confirmation, then switches Decky to the chosen third-party store and restarts the Decky service. The address is remembered in the list. Needs root. |
| Use official store | Switches back to Decky's official store and restarts the Decky service. Active when a third-party store is connected. Needs root. |

The subtitle shows which store is in use. Plugins from a third-party store are not reviewed by the Decky team — install only what you trust. Install / update and Repair do not change the store.

#### Where to show Decky in the headset

The Frame has no classic Quick Access Menu in VR, so the bundled SFH Frame Menu plugin adds Decky to other places. Here you choose where it appears.

| Checkbox | What happens |
|---|---|
| Left menu | Adds a "Decky" item to the Frame left menu, next to Settings. |
| Quick Settings | Adds a Decky tab to the Quick Settings popup on the Frame bar. |

You can clear both boxes: Decky is then not shown anywhere in the headset and opens only from SFH with "Open in headset". The headset menu will update the next time it opens. The boxes are active only when Steam is running and the SFH Frame Menu plugin is loaded in Decky; otherwise the subtitle says "Steam must be running and the SFH Frame Menu plugin must be installed in Decky". You can change the same setting inside the plugin, in the headset.

### Installed plugins section

The top row "Decky plugins" (folder `~/homebrew/plugins`) shows "Installed: N · updates: U".

| Button | What happens |
|---|---|
| Refresh list | Re-reads the plugin list and checks the store for updates. |
| Store in headset | Opens the Decky plugin store in the headset (Steam must be running). |
| Panel in headset | Opens the Decky panel in the headset. |

Below it, one row per plugin: a mark (check = turned on, cross = turned off), the name and the subtitle "version X · turned on/turned off · update available: Y".

| Button | What happens |
|---|---|
| Turn off / Turn on | Turns the plugin off or on. Decky restarts. |
| Update | Updates the plugin from the store. Active only when an update is available. |
| Remove | Deletes the plugin folder after confirmation. Decky restarts. |

All plugin buttons need root.

## Games tab

A list of installed Steam games from the main library (`~/.local/share/Steam/steamapps`). Tools such as Proton and Steam Linux Runtime are not listed. The top row "Steam games" reminds you where backups go: `~/steam_frame_helper_backups`. "Refresh" re-reads the list.

Each game's subtitle shows the AppID, the type (Windows (Proton), Android or Linux), the shader cache size and the number of backups. No root needed.

| Button | What happens |
|---|---|
| Back up | Saves an archive of the game's saves to `~/steam_frame_helper_backups/<AppID>/` (the file name is the date and time). For Windows games it takes the user profile in the Proton prefix; for Android games, the app data and shared storage; and it also includes the game's local Steam data. If no saves are found, it reports an error. |
| Restore | Opens a picker of backups by date and writes the chosen one over the current saves. The game must be closed. Active when backups exist. |
| Clear shaders | After confirmation, deletes the game's shader cache. The cache is rebuilt on the next launch, so the game may stutter for the first few minutes. Active when a cache exists. |
| Reset prefix (red) | After confirmation, first backs up the saves, then deletes the Proton prefix or the Android app data. Game settings and libraries installed into the prefix are lost; Steam recreates everything on launch. Available for Windows and Android games. |

## Apps tab

Installs regular Linux apps from Flathub (Flatpak, system-wide). The apps run in Desktop Mode.

| Element | What happens |
|---|---|
| Search box and "Search" | Searches Flathub (for example telegram, firefox, vlc). Enter in the box works like "Search". Shows up to 30 results. |
| Repair Flathub | Re-adds the Flathub repository, refreshes its address and key, and updates the app catalog. Helps when search or install fails. Needs root. |
| Install (in a result row) | Installs the app (root). It then appears in the "Installed" section. |
| Remove (in an installed row) | Removes the app after confirmation (root). App data in `~/.var/app` stays. |

Sections: Search results and Installed.

## Android tab

Installs an APK (and optional OBB files) as a VR app in your Steam library. It runs through Valve's Lepton compatibility layer. Use it only for apps you own legally.

### Android runtime section

#### Lepton 14 — Android 14 (SDK 34)

Valve's second Android runtime. Apps that need Android newer than 11 (minSdk above 30) require it. Steam installs the regular Lepton (Android 11) by itself, but downloads Lepton 14 only on request. A green check means Lepton 14 is installed.

| Button | What happens |
|---|---|
| Install | Asks Steam to download the Lepton 14 tool (same as the command `steam steam://install/5181730`). The download, about 500 MB, runs in Steam, and its progress shows in Steam downloads; while it runs, the row says "Downloading". No root needed. |

### Install APK section

| Element | What it does |
|---|---|
| Library name | The name the app gets in the Steam library. It must not contain "/". |
| Choose APK… | Pick an `.apk` file (the dialog opens in `~/Downloads`). If the name is empty, it is filled in from the file name. A line below shows the app ID, the minSdk and which environment "Auto" will pick. |
| Choose OBB… | Optional. Pick one or more `.obb` files (extra game data). |
| Android environment | "Auto (by minSdk from the APK)" picks a suitable environment from the APK's requirements; "Lepton — Android 11 (SDK 30)"; "Lepton 14 — Android 14 (SDK 34)". If the APK needs SDK above 30, only Lepton 14 works. Steam downloads Lepton 14 on the first launch that needs it, and it may be unavailable to some users. |
| Install | After confirmation, copies the APK and OBB files to `~/Games/<name>/` (hard links when the files are on the same disk, copies otherwise), adds a shortcut app to the Steam library and maps it to the chosen Lepton environment. Steam restarts; in the headset this takes about 30 seconds. |

### Installed section

Each app shows its environment, size in MB, OBB count, "has been launched" or "not launched yet", and its folder.

| Button | What happens |
|---|---|
| Log | Opens a window with the tail of the Lepton launch log (it has "Refresh" and "Logs folder" buttons in its header). Active once the app has been launched. |
| Folder | Opens the app's folder in the file manager. |
| Remove (red) | Asks what to remove: "Shortcut only" or "Shortcut and files" (which also deletes `~/Games/<name>`). The Lepton container with saves stays in both cases. Steam restarts. |

## Transfer tab

Two sections: Screenshots and Files to PC. Sending to the PC needs the [PC part](#pc-part).

### Screenshots section

Both rows use one background service, `sfh-screenshots`, which watches for new Steam screenshots and copies them. Only screenshots taken after you first turn it on are copied. Files are named "Game_name.jpg". No root needed. If both rows are off, the service stops.

| Row | Buttons | What happens |
|---|---|---|
| Copy screenshots to Frame (Pictures/Screenshots) | Turn on / Turn off | New screenshots are copied to `~/Pictures/Screenshots` on the Frame (a regular folder, easy to open in Desktop Mode). |
| Copy screenshots to PC (Pictures\SteamFrame) | Turn on / Turn off | New screenshots are put in a queue, and the PC agent collects them into the Pictures\SteamFrame folder. The subtitle shows whether the PC is connected and how many files are queued. |

### Files to PC section

Sends files and folders from the Frame to the PC. The row "Send to PC (Downloads\SteamFrame)" shows the PC link: "PC online (N s ago)", "PC offline for N min — are the PC and the agent running?" or "The PC agent hasn't connected yet".

| Button | What happens |
|---|---|
| Files… | Pick one or more files; they are put in the queue. |
| Folder… | Pick one or more folders; they are queued with their contents. |
| Clear queue | After confirmation, removes everything not yet sent from the queue. The originals on the Frame are not touched. |

How it works: a file goes into a queue on the Frame; the PC agent checks the queue every 5 seconds, takes everything into Downloads\SteamFrame and removes it from the queue. If the PC is off, files wait. Large files take no extra space on the Frame, because the queue holds hard links (a copy is made if the source is on another disk). The "Queue" list below shows the waiting files with their sizes and refreshes every 3 seconds. When it is empty it says "Empty — everything delivered".

## Developer tab

Two sections: Viewing and Remote access.

### Viewing section

#### Steam UI in a PC browser

Shows the Steam UI of the Frame in a browser on your PC and lets you control it with the mouse. Games are not shown: they are rendered straight into the headset and cannot be captured. You see the Steam windows themselves (menu, library, panels).

| Button | What happens |
|---|---|
| Turn on | Starts a small web server on the Frame (port 8091). The subtitle shows a link like `http://<Frame IP>:8091/?t=<token>`. |
| Copy link | Copies that link to the clipboard. Open it in a browser on a PC on the same network. |
| Turn off | Stops the server. |

The browser page has a dropdown of Steam windows, a "Back" button and a frames-per-second counter. Clicking the picture clicks in Steam, and the mouse wheel scrolls. Access is protected by the token in the link, but anyone who has the link and can reach your network can control the Steam UI. Do not leave it on when you do not need it.

### Remote access section

#### RDP: Wi-Fi without a password prompt

Useful if you connect to the Frame desktop through remote desktop (xrdp). The Plasma network widget scans Wi-Fi about every 10 seconds, and in a remote session every scan pops up a password dialog.

| Button | What happens |
|---|---|
| Turn on | Adds a system (polkit) rule that lets your user do exactly one thing without a password: scan Wi-Fi. Other network settings still need a password. Needs root. |
| Turn off | Removes that rule. Needs root. |

### Permissions section

#### Admin rights without a password

By default `sudo` asks for the user's password, SFH opens a password dialog for every action that needs root, and the desktop (in the headset or over RDP) sometimes shows system password dialogs, for example at shutdown. This feature removes the password in both places. A green check means no password is asked.

| Button | What happens |
|---|---|
| Turn on | Creates the rule `/etc/sudoers.d/zz-sfh-nopasswd` (`<user> ALL=(ALL) NOPASSWD: ALL`; checked with `visudo` first, a broken rule is never installed) and the polkit rule `/etc/polkit-1/rules.d/49-sfh-nopasswd.rules`, which lets your user do system actions without a password dialog. The polkit rule adds no new rights: with passwordless `sudo` root is available anyway. The password is asked once. |
| Turn off | Removes both rules: the password is asked again. |

Keep in mind: without a password, any program running as your user can get root. The rule lives in `/etc` and survives SteamOS updates, but a factory reset removes it.

Status checks (the green checks) never ask for a password: without passwordless sudo they run as the regular user.

## Decky quick menu (SFH Frame Menu)

The SFH Frame Menu plugin is installed together with Decky. It exists because the Frame has no classic Decky menu in VR.

How to open it:

1. In the headset, open the left menu and choose **Decky**, or open **Quick Settings** on the bar and go to the Decky tab (it depends on where you allowed it, see "Where to show Decky in the headset").
2. In the plugin list, choose **SFH Frame Menu**.

The plugin language follows the Steam client language (Russian or English) and does not depend on the language switcher in the SFH window.

The plugin has three sections.

| Section | What it does |
|---|---|
| Connection stats | The "Show in headset" switch shows or hides the connection stats window (the same as "Show / hide" in SFH). If the stats are not running, the switch is disabled and the hint tells you to turn them on in SFH (Tools → Network). |
| Turn off controllers | Three buttons with controller icons: left, both, right. They turn off the matching Frame controllers. A button is disabled when that controller is not connected. To turn a controller back on, press the Steam button. If this Steam version does not support it, the section says "Not available in this Steam version". |
| Where to show Decky | Two switches: "Left menu" (a "Decky" item on the left, next to Settings) and "Quick Settings" (a Decky tab in the Quick Settings popup). You can turn both off; Decky then opens only from SFH. The menu updates the next time it opens. The same setting is available in the SFH window. |

## PC part

The PC part (Windows 10/11) is needed for:

- copying screenshots from the Frame to the PC;
- receiving files queued on the Transfer tab;
- sending files from the PC to the Frame with the "Send to Frame" shortcut.

### Preparing the Frame

1. Set the user password: `passwd` in Konsole.
2. Turn on SSH: `sudo systemctl enable --now sshd`.
3. Find the Frame's IP address: in the Frame Wi-Fi settings, or with `ip addr` in Konsole. The address looks like `steamos@192.168.0.50`.

### Installing on the PC

1. Download the release archive from the project's GitHub releases page and unzip it.
2. Open PowerShell in the unzipped folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File steam_frame_helper\pc\install.ps1
```

The installer does the following:

1. Asks for the Frame address (`user@IP`, for example `steamos@192.168.0.50`) and saves it to `%USERPROFILE%\SteamFrameHelper\frame.txt`. If you type only an IP, `steamos@` is added.
2. Creates an SSH key if there is none and adds it to the Frame. It asks for the Frame password once.
3. Installs a hidden PC agent: a scheduled task `SteamFrameScreenshotSync` that starts when you log in to Windows. Every 5 seconds the agent picks up new screenshots from the Frame (into Pictures\SteamFrame) and files from the queue (into Downloads\SteamFrame).
4. Creates the "Send to Frame" shortcut on the desktop (the shortcut name depends on the Windows language).

Running the installer again updates the scripts and lets you change the Frame address.

### The "Send to Frame" shortcut

Opens a window titled "Send to Steam Frame". Add files or folders with the "Add files…" and "Add folder…" buttons, or drag them into the window, then press "Send". The items go to `~/Downloads` on the Frame. "Remove selected" removes entries from the send list. If the Frame cannot be reached, the window says so: check that the headset is on and on the same Wi-Fi network.

### What is where on the PC

| What | Where |
|---|---|
| Frame address | `%USERPROFILE%\SteamFrameHelper\frame.txt` |
| Agent scripts, the `screenshot_sync.log` log | `%USERPROFILE%\SteamFrameHelper\` |
| Screenshots from the Frame | Pictures\SteamFrame |
| Files from the Frame queue | Downloads\SteamFrame |

To remove the agent from the PC: run `Unregister-ScheduledTask -TaskName SteamFrameScreenshotSync` in PowerShell, then delete the `%USERPROFILE%\SteamFrameHelper` folder and the desktop shortcut.

## Updating and uninstalling

**Updating.** Run the same install command again. The app is updated, and your local settings and files are kept. Running services (connection stats, screenshot copying) restart on their own. The PC part is updated by running `install.ps1` again from a new release archive.

**Uninstalling the app:**

```bash
bash install.sh --uninstall
```

(`install.sh` is in the project repository; download it if you installed through `curl`). This removes the app, its menu entry and the `sfh-vr-hud` and `sfh-screenshots` services.

**What stays changed.** System changes are not rolled back. Undo them through SFH before uninstalling if you want them gone:

- the Wi-Fi region and the Wi-Fi power saving setting;
- Decky Loader, its plugins and the "Decky" library shortcut (the "Remove" button of Decky Loader removes Decky itself);
- the RDP Wi-Fi scan rule;
- an unlocked system partition (if you unlocked it);
- Flatpak apps and Android apps in the Steam library;
- game backups in `~/steam_frame_helper_backups`.

SteamOS updates may reset changes on the system partition.

## Troubleshooting and FAQ

| Problem | What to do |
|---|---|
| The headset's "Stop streaming" button does nothing | This happens when Decky and the Steam UI restarted during a stream (switching the store, installing or repairing Decky): the UI forgets the running session. Press "Stop streaming" in SFH (Tools → System → Quick actions). The headset button works again for the next stream. |
| "No root access (sudo/pkexec)" | The `steamos` user has no password. Set one with `passwd` in Konsole. After that the app can show the system password dialog. |
| The Decky item is not visible in the headset | On the Plugins tab, tick the place you want in "Where to show Decky in the headset" (with both cleared, Decky is not shown in the headset). Close and reopen the menu (it refreshes when it opens). Make sure Steam is running and the SFH Frame Menu plugin is installed. Press "Repair" in Decky Loader. You can also open Decky with "Open in headset". |
| The "Left menu" / "Quick Settings" boxes are greyed out | Steam must be running and the SFH Frame Menu plugin must be loaded. Press "Repair", then "Refresh list". |
| The connection stats are not visible in the headset | Press "Turn on" (check that the mark is a green check), then "Show / hide". The window appears only while SteamVR is running. Or turn on "Show in headset" in the plugin. |
| The "Show in headset" switch is disabled | The stats are not running: turn them on in SFH (Tools → Network). |
| The PC agent is offline | Check that the PC is on and you are logged in to Windows. Check the address in `%USERPROFILE%\SteamFrameHelper\frame.txt` (the Frame's IP may have changed). Check that the SSH key works: run `ssh steamos@IP` in PowerShell, and it should log in without a password. If not, run `install.ps1` again. Check that SSH is on on the Frame and that the Frame is not asleep. |
| `install.ps1` cannot log in to the Frame | Check the address, that a password is set on the Frame and that `sshd` is on. The PC needs the OpenSSH client. |
| The Steam wireless adapter stopped working | If the region is RU, press "Remove" in the region row or choose another region. |
| An Android app does not install | Check the APK: if minSdk is above 30, choose "Lepton 14" or "Auto". After launching it, use the "Log" button. |
| The app is in the wrong language | Use the language switcher in the window header. |

## Safety notes

- System features (region, Wi-Fi, Decky, system partition write access) change SteamOS settings. SteamOS updates may reset them. Unlock the system partition only if you know why, and lock it again.
- Do not pick the RU region on the Steam Frame.
- The "Steam UI in a PC browser" link gives control of the Steam UI to anyone who knows it. Turn the feature off when you do not need it.
- Decky Loader is third-party and plugins are written by different authors. Install only plugins you trust, especially from a third-party store.
- The Android feature is meant only for apps you own legally.
- Installing or removing Android apps, and installing, repairing or removing Decky, briefly restart Steam: save your progress first.
- License: PolyForm Noncommercial 1.0.0 (you may use, study, modify and share it, including your own changes, but not commercially).
