# Installs the Steam Frame agent on this PC (screenshots + files queued on the Frame):
# copies screenshot_sync.ps1 to %USERPROFILE%\SteamFrameHelper and registers
# a hidden scheduled task that starts it at logon. Run again to update.
# Uninstall: Unregister-ScheduledTask -TaskName SteamFrameScreenshotSync

$TaskName = 'SteamFrameScreenshotSync'
# Not under AppData: packaged (MSIX) apps that run this installer get AppData
# writes redirected into their private copy, invisible to Task Scheduler.
$Dir = Join-Path $env:USERPROFILE 'SteamFrameHelper'
$Script = Join-Path $Dir 'screenshot_sync.ps1'

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'screenshot_sync.ps1') $Script
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Dir 'run_hidden.vbs')

# conhost --headless keeps the console window from flashing at logon.
$action = New-ScheduledTaskAction -Execute 'conhost.exe' `
    -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
# Stopping the task does not end agents started earlier (older installs, manual runs):
# kill every running copy so exactly one agent serves the queues.
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like '*screenshot_sync.ps1*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Steam Frame Helper: copy screenshots from Steam Frame' `
    -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
