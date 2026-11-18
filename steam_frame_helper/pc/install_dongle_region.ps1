# Installs the dongle region agent (dongle_region.ps1): copies it to
# %USERPROFILE%\SteamFrameHelper and registers the scheduled task SteamFrameDongleRegion
# that starts it at logon with administrator rights (the driver request that sets the
# adapter's country needs them). Asks for elevation (UAC) by itself. Run again to update.
# Uninstall: Unregister-ScheduledTask -TaskName SteamFrameDongleRegion
param([switch]$Elevated)

$TaskName = 'SteamFrameDongleRegion'
$Dir = Join-Path $env:USERPROFILE 'SteamFrameHelper'
$Script = Join-Path $Dir 'dongle_region.ps1'

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($Elevated) { throw 'Administrator rights are needed (the UAC prompt was declined?)' }
    $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Elevated')
    exit $p.ExitCode
}

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'dongle_region.ps1') $Script

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute 'conhost.exe' `
    -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
# Match the installed agent's full path only: this installer's own name also ends
# in "dongle_region.ps1", and a looser pattern made it kill itself.
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like "*$Script*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $taskPrincipal -Settings $settings -Force `
    -Description 'Steam Frame Helper: keep the Valve wireless adapter on the Wi-Fi region set in SFH' |
    Out-Null
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
