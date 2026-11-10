English | [Русский](README.ru.md)

# Steam Frame Helper

A set of tweaks and utilities for the **Steam Frame** (SteamOS, aarch64) with a GTK3 window. Every feature is turned on and off with one button, and the app tells you what it changes on the system.

Full documentation: **[docs/GUIDE.en.md](docs/GUIDE.en.md)** (every tab, section and button).

## Features

Sections inside tabs collapse and remember their state. The language switcher (Русский / English) is in the window header, and the status line at the bottom shows what the app is doing.

- **Tools**
  - Wi-Fi region (kept after reboot) and Wi-Fi without power saving
  - **PC connection stats (in headset)**: a small window in the headset with live stream data: ping and packet loss as measured by Steam, traffic, signal and link speed of the Steam wireless adapter and your home Wi-Fi
  - system partition write access (Unlock / Lock), Restart Steam, Reboot
- **Plugins**: **Decky Loader** for ARM64 and Decky plugin management. The bundled *SFH Frame Menu* plugin adds Decky to the Frame left menu and Quick Settings, a switch for the connection stats, and buttons to turn off the left, right or both controllers
- **Games** and **Apps**: save backups, shader cache and prefix cleanup for Steam games; Flatpak apps from Flathub
- **Android**: install an APK (+ OBB) as a VR app in your Steam library through Lepton
- **Transfer**: copy screenshots to the Frame and to your PC, send files from the Frame to your PC
- **Developer**: the Steam UI in a PC browser, Wi-Fi without a password prompt in an RDP session

## Install on the Steam Frame

In Desktop Mode, open Konsole (or log in over SSH) and run:

```bash
curl -fsSL https://raw.githubusercontent.com/SantaClousG-G/steam-frame-helper/main/install.sh | bash
```

The app appears in the application menu as **Steam Frame Helper**. Run the same command again to update (your local settings and files are kept). To remove the app: `bash install.sh --uninstall` (system tweaks stay as they were).

The `steamos` user has no password by default. Features that change the system need root: the app tries passwordless `sudo`, then a system password dialog (`pkexec`). Set a password once with `passwd` in Konsole.

## PC part (Windows 10/11)

Needed for copying screenshots to the PC, receiving files from the Frame, and the "Send to Frame" desktop shortcut. On the Frame, set a password with `passwd` and turn on SSH: `sudo systemctl enable --now sshd`.

Download the release archive, unzip it and run in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File steam_frame_helper\pc\install.ps1
```

The installer asks for the Frame address (`user@IP`, for example `steamos@192.168.0.50`), sets up SSH key login (it asks the Frame password once) and installs a hidden PC agent and the shortcut. Details are in the [guide](docs/GUIDE.en.md#pc-part).

## AmneziaVPN

A native ARM64 build of AmneziaVPN is not part of the public release.

## License

[PolyForm Noncommercial 1.0.0](LICENSE): you may use, study, modify and share it, including your own changes, but not for commercial purposes.
