# Installs Frame Send: copies FrameSend.ps1 to %USERPROFILE%\SteamFrameHelper and
# puts an "Отправить на Frame" shortcut on the desktop. Run again to update.
# Not under AppData: packaged (MSIX) apps that run this installer get AppData
# writes redirected into their private copy, invisible to the rest of Windows.

$Dir = Join-Path $env:USERPROFILE 'SteamFrameHelper'
$Script = Join-Path $Dir 'FrameSend.ps1'
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

# Windows PowerShell 5.1 reads scripts without a BOM as ANSI: save as UTF-8 with BOM
# so the Russian UI strings survive.
$text = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot 'FrameSend.ps1'), [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($Script, $text, (New-Object System.Text.UTF8Encoding($true)))

$shell = New-Object -ComObject WScript.Shell
$lnkPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Отправить на Frame.lnk'
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = 'powershell.exe'
$lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""
$lnk.WorkingDirectory = $Dir
$lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,146"
$lnk.Description = 'Отправить файлы и папки в Загрузки на Steam Frame'
$lnk.Save()

Write-Output "Installed: $Script"
Write-Output "Shortcut:  $lnkPath"
