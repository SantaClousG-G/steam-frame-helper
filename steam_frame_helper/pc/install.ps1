# Steam Frame Helper — PC side setup (Windows 10/11, Windows PowerShell 5.1).
#   1. asks for the Frame address (user@host) and saves it to
#      %USERPROFILE%\SteamFrameHelper\frame.txt;
#   2. sets up SSH key login to the Frame (creates a key if there is none; the Frame
#      password is asked once by ssh itself to add the key);
#   3. installs the PC agent (screenshots / files from the Frame) and the desktop
#      shortcut "Отправить на Frame".
# Run again any time to change the address or update the scripts.
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1 [-Frame steamos@192.168.0.50]
param([string]$Frame = '')

$ErrorActionPreference = 'Stop'
$IsRu = (Get-UICulture).TwoLetterISOLanguageName -eq 'ru'
function T($ru, $en) { if ($IsRu) { $ru } else { $en } }
$Dir = Join-Path $env:USERPROFILE 'SteamFrameHelper'
$ConfigFile = Join-Path $Dir 'frame.txt'
$SshExe = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
$KeygenExe = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh-keygen.exe'
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

if (-not (Test-Path -LiteralPath $SshExe)) {
    throw 'OpenSSH client not found. Settings → System → Optional features → add "OpenSSH Client".'
}

# ---------- 1. Frame address ----------
$current = ''
if (Test-Path -LiteralPath $ConfigFile) {
    $current = "$(Get-Content -LiteralPath $ConfigFile -TotalCount 1)".Trim()
}
if (-not $Frame) {
    $hint = if ($current) { " [$current]" } else { ' (' + (T 'например' 'e.g.') + ' steamos@192.168.0.50)' }
    $Frame = (Read-Host (T "Адрес Steam Frame: пользователь@IP$hint" "Steam Frame address: user@IP$hint")).Trim()
    if (-not $Frame) { $Frame = $current }
}
if (-not $Frame) { throw (T 'Адрес Frame не указан' 'Frame address not set') }
if (-not $Frame.Contains('@')) { $Frame = "steamos@$Frame" }
Set-Content -LiteralPath $ConfigFile -Value $Frame -Encoding ASCII
Write-Output "Frame: $Frame"

# ---------- 2. SSH key login ----------
$key = Join-Path $env:USERPROFILE '.ssh\id_ed25519'
if (-not (Test-Path -LiteralPath $key)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $key) | Out-Null
    & $KeygenExe -t ed25519 -N '""' -f $key -q
}
& $SshExe -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new $Frame true 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Output (T 'Добавляю ключ на Frame — ssh спросит пароль пользователя Frame (один раз).' 'Adding the key to the Frame. ssh will ask for the Frame user password (once).')
    $pub = Get-Content -LiteralPath "$key.pub" -Raw
    $pub | & $SshExe -o StrictHostKeyChecking=accept-new $Frame `
        'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys'
    & $SshExe -o BatchMode=yes -o ConnectTimeout=5 $Frame true
    if ($LASTEXITCODE -ne 0) { throw (T 'Не удалось войти на Frame по ключу. Проверь адрес и что на Frame включён SSH.' 'Could not sign in to the Frame with the key. Check the address and that SSH is turned on on the Frame.') }
}
Write-Output (T 'SSH по ключу работает.' 'SSH key login works.')

# ---------- 3. agent + shortcut ----------
# Scripts come from this folder (release archive) or, when run as a one-liner, from GitHub.
$src = $PSScriptRoot
if (-not $src) {
    $src = Join-Path $env:TEMP 'sfh-pc'
    New-Item -ItemType Directory -Force -Path $src | Out-Null
    $base = 'https://raw.githubusercontent.com/SantaClousG-G/steam-frame-helper/main/steam_frame_helper/pc'
    foreach ($f in 'screenshot_sync.ps1', 'install_pc_agent.ps1', 'FrameSend.ps1', 'install_frame_send.ps1') {
        Invoke-WebRequest -UseBasicParsing "$base/$f" -OutFile (Join-Path $src $f)
    }
}
& (Join-Path $src 'install_pc_agent.ps1')
& (Join-Path $src 'install_frame_send.ps1')
Write-Output (T 'Готово.' 'Done.')
