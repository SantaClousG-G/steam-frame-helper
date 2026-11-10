# Steam Frame Helper - PC agent. Runs hidden at logon (scheduled task) and polls the
# Steam Frame over SSH every few seconds:
#   * screenshots: the Frame watcher puts new screenshots into its outbox when
#     "copy to PC" is enabled; they go to Pictures\SteamFrame;
#   * files: items queued on the Frame (SFH tab "Передача", tools/to_pc.py) are
#     streamed to Downloads\SteamFrame, folders included.
# Delivered items are removed from the Frame queues.

# Frame address (user@host), written by pc\install.ps1. Re-read every poll, so a
# changed address works without restarting the agent.
$ConfigFile = Join-Path $env:USERPROFILE 'SteamFrameHelper\frame.txt'
function Get-FrameAddress {
    if (Test-Path -LiteralPath $ConfigFile) {
        return "$(Get-Content -LiteralPath $ConfigFile -TotalCount 1)".Trim()
    }
    return ''
}
$Frame = Get-FrameAddress
$State = '.local/share/steam_frame_helper'
$Remote = "$State/outbox"
$FilesQueue = "$State/to-pc"
$Heartbeat = "$State/pc_heartbeat"
$Dest = Join-Path ([Environment]::GetFolderPath('MyPictures')) 'SteamFrame'
$PollSeconds = 5
# ServerAlive*: when the Frame sleeps or reboots mid-connection, drop the dead session
# after ~15 s instead of hanging forever (that froze the agent once).
# -n: never read stdin. The agent runs under a hidden console, and ssh.exe holding
# that inherited stdin sometimes never exits after the remote command finished —
# that froze the agent (the remote session was done, the client kept waiting).
$SshOpts = @('-n', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
             '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3')
$ScpOpts = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
             '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3')
$SshExe = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
$TarExe = Join-Path $env:SystemRoot 'System32\tar.exe'
$Log = Join-Path $PSScriptRoot 'screenshot_sync.log'
$Allowed = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-'
$Separator = '@@SFH-FILES@@'

# File names from the Frame are UTF-8. Child stdin must not get a BOM: Process
# StandardInput writes one in UTF-8 mode, which would corrupt the tar stream.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)

function Get-DownloadsDir {
    try {
        $p = (New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    } catch { }
    return (Join-Path $env:USERPROFILE 'Downloads')
}
$FilesDest = Join-Path (Get-DownloadsDir) 'SteamFrame'

function Write-Log($Text) {
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Text
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Quote-Remote([string]$Name) {
    return "'" + $Name.Replace("'", "'\''") + "'"
}

function Get-UniquePath([string]$Dir, [string]$Name) {
    $target = Join-Path $Dir $Name
    $stem = [IO.Path]::GetFileNameWithoutExtension($Name)
    $ext = [IO.Path]::GetExtension($Name)
    $n = 1
    while (Test-Path -LiteralPath $target) {
        $target = Join-Path $Dir ("{0} ({1}){2}" -f $stem, $n, $ext)
        $n++
    }
    return $target
}

function Receive-QueuedItem([string]$Name) {
    # ssh "tar -c" on the Frame -> tar.exe -x here, streamed through .NET (no cmd.exe,
    # PowerShell pipes between native programs are not binary-safe).
    $incoming = Join-Path $FilesDest '.incoming'
    Remove-Item -LiteralPath $incoming -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $incoming | Out-Null

    $q = Quote-Remote $Name
    $sshPsi = New-Object System.Diagnostics.ProcessStartInfo
    $sshPsi.FileName = $SshExe
    # --format=posix (pax) stores names explicitly as UTF-8; with GNU tar's default
    # format Windows tar.exe decodes non-ASCII names in the local code page.
    $sshPsi.Arguments = ($SshOpts -join ' ') + " $Frame `"cd $FilesQueue && tar --format=posix -cf - -- $q`""
    $sshPsi.UseShellExecute = $false
    $sshPsi.CreateNoWindow = $true
    $sshPsi.RedirectStandardOutput = $true
    $sshPsi.RedirectStandardError = $true

    $tarPsi = New-Object System.Diagnostics.ProcessStartInfo
    $tarPsi.FileName = $TarExe
    $tarPsi.Arguments = "-xf - -C `"$incoming`""
    $tarPsi.UseShellExecute = $false
    $tarPsi.CreateNoWindow = $true
    $tarPsi.RedirectStandardInput = $true
    $tarPsi.RedirectStandardError = $true

    $tar = [System.Diagnostics.Process]::Start($tarPsi)
    $tarErr = $tar.StandardError.ReadToEndAsync()
    $ssh = [System.Diagnostics.Process]::Start($sshPsi)
    $sshErr = $ssh.StandardError.ReadToEndAsync()
    $copy = $ssh.StandardOutput.BaseStream.CopyToAsync($tar.StandardInput.BaseStream, 1MB)
    $copy.Wait()
    $tar.StandardInput.Close()
    $ssh.WaitForExit(); $tar.WaitForExit()

    if ($copy.IsFaulted -or $ssh.ExitCode -ne 0 -or $tar.ExitCode -ne 0) {
        Write-Log ("file failed: {0}: ssh={1} tar={2} {3} {4}" -f $Name, $ssh.ExitCode, $tar.ExitCode,
                   $sshErr.Result.Trim(), $tarErr.Result.Trim())
        return $false
    }
    $received = Get-ChildItem -LiteralPath $incoming -Force | Select-Object -First 1
    if (-not $received) { Write-Log "file failed: $Name (empty)"; return $false }
    $target = Get-UniquePath $FilesDest $received.Name
    Move-Item -LiteralPath $received.FullName -Destination $target
    Remove-Item -LiteralPath $incoming -Recurse -Force -ErrorAction SilentlyContinue
    Write-Log "file received: $Name -> $target"
    return $true
}

Write-Log "started, screenshots: $Dest, files: $FilesDest"
while ($true) {
    $Frame = Get-FrameAddress
    if (-not $Frame) {
        Start-Sleep -Seconds 30      # not configured yet (pc\install.ps1 writes frame.txt)
        continue
    }
    $cmd ="mkdir -p $State && touch $Heartbeat; " +
           "(cd $Remote 2>/dev/null && ls -1 -- *.jpg 2>/dev/null); echo $Separator; " +
           "(cd $FilesQueue 2>/dev/null && ls -1A | grep -v '^\.part-'); true"
    # "; true": grep exits 1 on an empty files queue, which used to make the whole
    # poll look failed, so screenshots were skipped whenever no files were queued.
    $output = & $SshExe @SshOpts $Frame $cmd
    if ($LASTEXITCODE -eq 0 -and $output) {
        $lines = @($output)
        $sep = [Array]::IndexOf($lines, $Separator)
        if ($sep -lt 0) { $sep = $lines.Count }
        $shots = if ($sep -gt 0) { $lines[0..($sep - 1)] } else { @() }
        $files = if ($sep + 1 -lt $lines.Count) { $lines[($sep + 1)..($lines.Count - 1)] } else { @() }

        if ($shots.Count -gt 0) { New-Item -ItemType Directory -Force -Path $Dest | Out-Null }
        foreach ($name in $shots) {
            $name = "$name".Trim()
            # Names come from the Frame watcher: ASCII letters, digits, - _ . only.
            $bad = @($name.ToCharArray() | Where-Object { $Allowed.IndexOf($_) -lt 0 })
            if (-not $name -or $bad.Count -gt 0 -or -not $name.EndsWith('.jpg')) { continue }
            & scp @ScpOpts -p "${Frame}:$Remote/$name" (Join-Path $Dest $name)
            if ($LASTEXITCODE -eq 0) {
                & $SshExe @SshOpts $Frame "rm -f -- $Remote/$name" | Out-Null
                Write-Log "copied $name"
            } else {
                Write-Log "scp failed for $name"
            }
        }

        if ($files.Count -gt 0) { New-Item -ItemType Directory -Force -Path $FilesDest | Out-Null }
        foreach ($name in $files) {
            $name = "$name"
            if (-not $name -or $name.Contains('/')) { continue }
            if (Receive-QueuedItem $name) {
                & $SshExe @SshOpts $Frame ("rm -rf -- $FilesQueue/" + (Quote-Remote $name)) | Out-Null
            }
        }
    }
    Start-Sleep -Seconds $PollSeconds
}
