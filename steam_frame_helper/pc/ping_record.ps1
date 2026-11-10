# Continuous ping from the PC to the Steam Frame, 4 samples per second per target, for
# streaming diagnostics. By default pings the Frame address from frame.txt (the router
# path); add -Adapter <ip> to also ping the Frame over the Steam wireless adapter
# (the Frame side of the adapter link, e.g. 10.x.x.1 - see `ip addr show wlanap`).
# Usage: ping_record.ps1 [-Seconds 600] [-Out file.csv] [-Frame host] [-Adapter ip]
param(
    [int]$Seconds = 600,
    [string]$Out = "$env:USERPROFILE\SteamFrameHelper\ping_record.csv",
    [string]$Frame = '',
    [string]$Adapter = ''
)

if (-not $Frame) {
    $config = Join-Path $env:USERPROFILE 'SteamFrameHelper\frame.txt'
    if (Test-Path -LiteralPath $config) {
        $Frame = "$(Get-Content -LiteralPath $config -TotalCount 1)".Trim()
    }
}
if ($Frame.Contains('@')) { $Frame = $Frame.Substring($Frame.IndexOf('@') + 1) }
if (-not $Frame) { throw 'Frame address unknown: pass -Frame or run pc\install.ps1 first' }

$targets = [ordered]@{ router = $Frame }
if ($Adapter) { $targets.adapter = $Adapter }
$ping = New-Object System.Net.NetworkInformation.Ping
"time,path,ms" | Set-Content -Path $Out -Encoding ASCII
$end = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $end) {
    foreach ($k in $targets.Keys) {
        $t = Get-Date -Format 'HH:mm:ss.fff'
        try {
            $r = $ping.Send($targets[$k], 1000)
            $ms = if ($r.Status -eq 'Success') { $r.RoundtripTime } else { -1 }
        } catch { $ms = -1 }
        Add-Content -Path $Out -Value "$t,$k,$ms" -Encoding ASCII
    }
    Start-Sleep -Milliseconds 250
}
"done: $Out"
