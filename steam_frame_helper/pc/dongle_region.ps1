# Steam Frame Helper - dongle region agent. Runs elevated at logon (scheduled task
# SteamFrameDongleRegion, installed by install_dongle_region.ps1).
#
# Why: the Valve USB wireless adapter (VID_28DE PID_2432, Realtek driver rtwlanuval)
# takes its regulatory country from the beacons of nearby Wi-Fi networks (802.11d).
# When they all say a country whose table in the adapter has no 6 GHz channels (RU,
# for example), the adapter turns its 6 GHz radio off, never sees the Frame's 6 GHz
# access point, and Steam falls back to a shared 5 GHz channel. Setting the country
# by hand ("manual" mode) brings 6 GHz back, but the adapter forgets it when it is
# re-plugged. This agent re-applies it.
#
# Which country: the Wi-Fi region chosen in SFH on the Frame (Settings, region:
# WIRELESS_REGDOM in /etc/conf.d/wireless-regdom), read over SSH. The file
# dongle_region.txt next to this script, when it holds a two-letter code, overrides
# it. No region anywhere = the agent does nothing.
#
# The adapter is only queried (its country, a cheap driver request) every few
# seconds; the country is written only when it differs from the target, at most
# once a minute. Log: dongle_region.log next to this script.

$ErrorActionPreference = 'Stop'
$Dir = Join-Path $env:USERPROFILE 'SteamFrameHelper'
$ConfigFile = Join-Path $Dir 'frame.txt'
$OverrideFile = Join-Path $Dir 'dongle_region.txt'
$Log = Join-Path $Dir 'dongle_region.log'
$SshExe = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
$SshOpts = @('-n', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
             '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3')
$PollSeconds = 15
$RegionRefreshSeconds = 300
$RetrySeconds = 60

function Write-Log([string]$msg) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    try {
        if ((Test-Path -LiteralPath $Log) -and (Get-Item -LiteralPath $Log).Length -gt 1MB) {
            Move-Item -Force -LiteralPath $Log -Destination "$Log.old"
        }
        Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
    } catch { }
}

# ---------- driver access (WLAN API, vendor "IHV" control requests) ----------
Add-Type -ErrorAction SilentlyContinue -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SfhWlan {
    [DllImport("wlanapi.dll")]
    public static extern uint WlanOpenHandle(uint clientVersion, IntPtr reserved,
        out uint negotiatedVersion, out IntPtr handle);
    [DllImport("wlanapi.dll")]
    public static extern uint WlanCloseHandle(IntPtr handle, IntPtr reserved);
    [DllImport("wlanapi.dll")]
    public static extern uint WlanIhvControl(IntPtr handle, ref Guid iface, int type,
        uint inSize, byte[] inBuf, uint outSize, byte[] outBuf, out uint returned);
}
'@

# Request codes of the Realtek driver's diagnostic interface. Parsed from text:
# PowerShell 5.1 reads a literal like 0xff81521f as a negative Int32.
function U32([string]$hex) { [Convert]::ToUInt32($hex, 16) }
$OidCountry = U32 'ff81521f'   # read: two ASCII letters of the current country
$OidCommand = U32 'ff818040'   # write: a diagnostic command line
$OidDone    = U32 'ff818041'   # read: 1 when the last command has finished
$OidOutput  = U32 'ff818042'   # read: the command's text output, block by block
$RequestTag = U32 '814ce000'

# Request: ten uint32 words (sizes, a fixed tag, the request code), then the body.
# The driver answers in a buffer of the same size, echoing the first 28 bytes.
function New-Request([uint32]$oid, [byte[]]$body) {
    if (-not $body) { $body = New-Object byte[] 300 }
    $n = [uint32]$body.Length
    $words = @(($n + 36), $RequestTag, 4, 1, 7, ($n + 40), $oid, ($n + 24), ($n + 24), $n)
    $buf = New-Object byte[] (40 + $n)
    for ($i = 0; $i -lt 10; $i++) {
        [BitConverter]::GetBytes([uint32]$words[$i]).CopyTo($buf, 4 * $i)
    }
    $body.CopyTo($buf, 40)
    , $buf
}

function Invoke-Driver([IntPtr]$handle, [Guid]$iface, [uint32]$oid, [byte[]]$body) {
    $req = New-Request $oid $body
    $resp = [byte[]]$req.Clone()
    $got = [uint32]0
    $rc = [SfhWlan]::WlanIhvControl($handle, [ref]$iface, 1, [uint32]$req.Length, $req,
                                    [uint32]$resp.Length, $resp, [ref]$got)
    if ($rc -ne 0) { throw "WlanIhvControl: Win32 error $rc" }
    if ($got -lt 40 -or $got -gt $resp.Length) { throw 'driver: bad reply size' }
    for ($i = 0; $i -lt 28; $i++) {
        if ($req[$i] -ne $resp[$i]) { throw 'driver: reply does not match the request' }
    }
    $len = [BitConverter]::ToUInt32($resp, 28)
    if ([BitConverter]::ToUInt32($resp, 32) -ne 0 -or $len -gt [BitConverter]::ToUInt32($resp, 36) -or
        40 + $len -gt $got) { throw 'driver: bad reply length' }
    if ($len -eq 0) { return , (New-Object byte[] 0) }
    , $resp[40..(40 + $len - 1)]
}

function Get-DongleCountry([IntPtr]$handle, [Guid]$iface) {
    $b = [byte[]](Invoke-Driver $handle $iface $OidCountry $null)
    if ($b.Count -ne 2 -or ($b[0] -eq 0 -and $b[1] -eq 0)) { return '' }
    [Text.Encoding]::ASCII.GetString($b)
}

function Test-CommandDone([IntPtr]$handle, [Guid]$iface) {
    $b = [byte[]](Invoke-Driver $handle $iface $OidDone $null)
    $b.Count -eq 4 -and [BitConverter]::ToUInt32($b, 0) -eq 1
}

# Runs one diagnostic command (words of up to 15 ASCII chars) and returns its text.
function Invoke-DongleCommand([IntPtr]$handle, [Guid]$iface, [string[]]$words, [uint32]$kind) {
    $body = New-Object byte[] 336
    [BitConverter]::GetBytes($kind).CopyTo($body, 8)
    [BitConverter]::GetBytes([uint32]3).CopyTo($body, 12)
    for ($i = 0; $i -lt $words.Count; $i++) {
        [Text.Encoding]::ASCII.GetBytes($words[$i]).CopyTo($body, 16 + 16 * $i)
    }
    [void](Test-CommandDone $handle $iface)          # clear a stale "done" flag
    [void](Invoke-Driver $handle $iface $OidCommand $body)
    $done = $false
    for ($i = 0; $i -lt 20 -and -not $done; $i++) {
        Start-Sleep -Milliseconds 100
        $done = Test-CommandDone $handle $iface
    }
    if (-not $done) { throw 'driver: command did not finish in 2 s' }
    $text = New-Object Collections.Generic.List[byte]
    for ($i = 0; $i -lt 64; $i++) {
        $blk = [byte[]](Invoke-Driver $handle $iface $OidOutput $null)
        if ($blk.Count -lt 16) { break }
        $status = [BitConverter]::ToUInt32($blk, 4)
        $len = [BitConverter]::ToUInt32($blk, 12)
        if ($len -gt 200 -or $blk.Count -ne 16 + $len) { break }
        if ($len -gt 0) { $text.AddRange([byte[]]$blk[16..($blk.Count - 1)]) }
        $zero = $text.IndexOf([byte]0)
        if ($zero -ge 0) { $text = $text.GetRange(0, $zero); break }
        if ($status -eq 0) { break }
    }
    ([Text.Encoding]::ASCII.GetString($text.ToArray())) -replace "`r", ''
}

# ---------- target region ----------
$script:FrameRegion = ''
$script:FrameRegionAt = [datetime]::MinValue

function Get-TargetRegion {
    if (Test-Path -LiteralPath $OverrideFile) {
        $o = "$(Get-Content -LiteralPath $OverrideFile -TotalCount 1)".Trim().ToUpperInvariant()
        if ($o -match '^[A-Z]{2}$' -and $o -ne '00') { return $o }
    }
    if (((Get-Date) - $script:FrameRegionAt).TotalSeconds -ge $RegionRefreshSeconds) {
        $frame = ''
        if (Test-Path -LiteralPath $ConfigFile) {
            $frame = "$(Get-Content -LiteralPath $ConfigFile -TotalCount 1)".Trim()
        }
        if ($frame) {
            $out = & $SshExe @SshOpts $frame "sed -n 's/^WIRELESS_REGDOM=.\(..\).*/\1/p' /etc/conf.d/wireless-regdom 2>/dev/null | head -n1" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $code = "$out".Trim().ToUpperInvariant()
                if ($code -ne $script:FrameRegion) { Write-Log "region in SFH on the Frame: '$code'" }
                $script:FrameRegion = if ($code -match '^[A-Z]{2}$' -and $code -ne '00') { $code } else { '' }
                $script:FrameRegionAt = Get-Date
            }
        }
    }
    $script:FrameRegion
}

function Get-Dongle {
    Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object {
        $_.PnPDeviceID -match '^USB\\VID_28DE&PID_2432'
    } | Select-Object -First 1
}

# ---------- main loop ----------
$created = $false
$mutex = New-Object Threading.Mutex($true, 'Global\SteamFrameHelperDongleRegion', [ref]$created)
if (-not $created) { exit 0 }                          # another copy is running

Write-Log 'agent started'
$lastTry = @{}                                          # adapter GUID -> time of the last write
$lastSeen = ''
while ($true) {
    try {
        $dongle = Get-Dongle
        if (-not $dongle) {
            if ($lastSeen) { Write-Log 'adapter unplugged'; $lastSeen = '' }
        } else {
            $target = Get-TargetRegion
            $iface = [Guid]$dongle.InterfaceGuid
            $h = [IntPtr]::Zero
            $neg = [uint32]0
            $rc = [SfhWlan]::WlanOpenHandle(2, [IntPtr]::Zero, [ref]$neg, [ref]$h)
            if ($rc -ne 0) { throw "WlanOpenHandle: Win32 error $rc" }
            try {
                $country = Get-DongleCountry $h $iface
                $key = "$iface"
                if ($lastSeen -ne "$key/$country") {
                    Write-Log "adapter: country '$country', target '$target'"
                    $lastSeen = "$key/$country"
                }
                $due = -not $lastTry.ContainsKey($key) -or
                       ((Get-Date) - $lastTry[$key]).TotalSeconds -ge $RetrySeconds
                if ($target -and $country -ne $target -and $due) {
                    $lastTry[$key] = Get-Date
                    $reply = Invoke-DongleCommand $h $iface @('67', $target) 29
                    $after = Get-DongleCountry $h $iface
                    $info = Invoke-DongleCommand $h $iface @('echo', 'core', '6g_info') 0
                    $g6 = ($info -split "`n" | Where-Object { $_ -match '6G' } |
                           ForEach-Object { $_.Trim() }) -join ' | '
                    Write-Log ("set $country -> $target`: reply '{0}', now '{1}', {2}" -f $reply.Trim(), $after, $g6)
                    $lastSeen = "$key/$after"
                }
            } finally {
                [void][SfhWlan]::WlanCloseHandle($h, [IntPtr]::Zero)
            }
        }
    } catch {
        Write-Log "error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $PollSeconds
}
