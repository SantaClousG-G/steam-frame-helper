# Frame Send — copies files and folders from this PC to ~/Downloads on the Steam Frame.
# Part of Steam Frame Helper. Uses the SSH key login set up for the Frame and the
# tar/ssh tools built into Windows: tar -c | ssh "tar -x" keeps folders intact and is
# much faster than scp for many small files. After each item the size on the Frame
# is compared with the local one.

$RemoteDir = '~/Downloads'
$TarExe = Join-Path $env:SystemRoot 'System32\tar.exe'
$SshExe = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# Frame address (user@host), written by pc\install.ps1.
$ConfigFile = Join-Path $env:USERPROFILE 'SteamFrameHelper\frame.txt'
$Frame = ''
if (Test-Path -LiteralPath $ConfigFile) {
    $Frame = "$(Get-Content -LiteralPath $ConfigFile -TotalCount 1)".Trim()
}
if (-not $Frame) {
    [System.Windows.Forms.MessageBox]::Show(
        "Адрес Steam Frame не задан. Запусти pc\install.ps1 из Steam Frame Helper.",
        'Отправить на Frame') | Out-Null
    exit 1
}

# ---------- helpers ----------

function Get-LocalSize([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return (Get-Item -LiteralPath $Path).Length
    }
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
    if ($sum) { return [int64]$sum } else { return [int64]0 }
}

function Format-Size([int64]$Bytes) {
    if ($Bytes -ge 1GB) { return '{0:N1} ГБ' -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return '{0:N1} МБ' -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return '{0:N0} КБ' -f ($Bytes / 1KB) }
    return "$Bytes Б"
}

function Quote-Remote([string]$Name) {
    # single-quote for the remote POSIX shell
    return "'" + $Name.Replace("'", "'\''") + "'"
}

function Get-RemoteSize([string]$Name) {
    $q = Quote-Remote $Name
    $out = & ssh -o BatchMode=yes -o ConnectTimeout=5 $Frame "du -sb --apparent-size $RemoteDir/$q 2>/dev/null | cut -f1"
    if ($LASTEXITCODE -eq 0 -and "$out".Trim() -match '^\d+$') { return [int64]"$out".Trim() }
    return [int64]-1
}

# ---------- UI ----------

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Отправка на Steam Frame'
$form.Size = New-Object System.Drawing.Size(640, 480)
$form.MinimumSize = New-Object System.Drawing.Size(520, 380)
$form.StartPosition = 'CenterScreen'
$form.AllowDrop = $true
$form.Font = New-Object System.Drawing.Font('Segoe UI', 9.5)

$header = New-Object System.Windows.Forms.Label
$header.Text = "Куда: $Frame  →  $RemoteDir`nДобавь файлы или папки кнопками или перетащи их в окно."
$header.Dock = 'Top'
$header.Height = 46
$header.Padding = New-Object System.Windows.Forms.Padding(8, 6, 8, 0)

$list = New-Object System.Windows.Forms.ListBox
$list.Dock = 'Fill'
$list.SelectionMode = 'MultiExtended'
$list.HorizontalScrollbar = $true
$list.AllowDrop = $true

$buttons = New-Object System.Windows.Forms.FlowLayoutPanel
$buttons.Dock = 'Bottom'
$buttons.Height = 40
$buttons.Padding = New-Object System.Windows.Forms.Padding(6, 4, 6, 4)

function New-Button([string]$Text) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $Text
    $b.AutoSize = $true
    $b.Height = 30
    $buttons.Controls.Add($b) | Out-Null
    return $b
}
$btnFiles = New-Button 'Добавить файлы…'
$btnFolder = New-Button 'Добавить папку…'
$btnRemove = New-Button 'Убрать выбранное'
$btnSend = New-Button 'Отправить'
$btnSend.Font = New-Object System.Drawing.Font('Segoe UI', 9.5, [System.Drawing.FontStyle]::Bold)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Dock = 'Bottom'
$progress.Height = 14
$progress.Style = 'Continuous'

$status = New-Object System.Windows.Forms.TextBox
$status.Dock = 'Bottom'
$status.Height = 110
$status.Multiline = $true
$status.ReadOnly = $true
$status.ScrollBars = 'Vertical'

$form.Controls.Add($list)
$form.Controls.Add($header)
$form.Controls.Add($buttons)
$form.Controls.Add($progress)
$form.Controls.Add($status)

function Write-Status([string]$Text) {
    $status.AppendText(('{0:HH:mm:ss}  {1}' -f (Get-Date), $Text) + [Environment]::NewLine)
}

function Add-Paths([string[]]$Paths) {
    foreach ($p in $Paths) {
        if ($p -and (Test-Path -LiteralPath $p) -and -not $list.Items.Contains($p)) {
            $list.Items.Add($p) | Out-Null
        }
    }
}

$btnFiles.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Multiselect = $true
    $dlg.Title = 'Файлы для отправки на Frame'
    if ($dlg.ShowDialog($form) -eq 'OK') { Add-Paths $dlg.FileNames }
})

$btnFolder.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'Папка для отправки на Frame'
    if ($dlg.ShowDialog($form) -eq 'OK') { Add-Paths @($dlg.SelectedPath) }
})

$btnRemove.Add_Click({
    foreach ($item in @($list.SelectedItems)) { $list.Items.Remove($item) }
})

$onDragEnter = {
    param($s, $e)
    if ($e.Data.GetDataPresent([System.Windows.Forms.DataFormats]::FileDrop)) { $e.Effect = 'Copy' }
}
$onDragDrop = {
    param($s, $e)
    Add-Paths ([string[]]$e.Data.GetData([System.Windows.Forms.DataFormats]::FileDrop))
}
$form.Add_DragEnter($onDragEnter); $form.Add_DragDrop($onDragDrop)
$list.Add_DragEnter($onDragEnter); $list.Add_DragDrop($onDragDrop)

# ---------- sending ----------

function Set-Busy([bool]$Busy) {
    foreach ($b in @($btnFiles, $btnFolder, $btnRemove, $btnSend)) { $b.Enabled = -not $Busy }
    $list.Enabled = -not $Busy
}

function Send-Item([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    # (Split-Path -LiteralPath ... -Parent is an invalid parameter set in PowerShell 5.1)
    $parent = [System.IO.Path]::GetDirectoryName($item.FullName.TrimEnd('\'))
    $name = $item.Name
    $localSize = Get-LocalSize $item.FullName
    Write-Status "Отправка: $name ($(Format-Size $localSize))"

    # tar.exe stdout is copied into ssh.exe stdin by .NET streams: no cmd.exe in between
    # (cmd parses %, ^, & in file names), and PowerShell 5.1 pipes between native
    # programs are not binary-safe. Each side's errors are captured separately.
    $tarPsi = New-Object System.Diagnostics.ProcessStartInfo
    $tarPsi.FileName = $TarExe
    $tarPsi.Arguments = "-cf - -C `"$parent`" `"$name`""
    $tarPsi.UseShellExecute = $false
    $tarPsi.CreateNoWindow = $true
    $tarPsi.RedirectStandardOutput = $true
    $tarPsi.RedirectStandardError = $true

    $remote = "mkdir -p $RemoteDir && tar -xf - -C $RemoteDir"
    $sshPsi = New-Object System.Diagnostics.ProcessStartInfo
    $sshPsi.FileName = $SshExe
    $sshPsi.Arguments = "-o BatchMode=yes -o ServerAliveInterval=15 $Frame `"$remote`""
    $sshPsi.UseShellExecute = $false
    $sshPsi.CreateNoWindow = $true
    $sshPsi.RedirectStandardInput = $true
    $sshPsi.RedirectStandardError = $true

    # Process.StandardInput is a StreamWriter in Console.InputEncoding with AutoFlush:
    # with UTF-8 (code page 65001) it writes a BOM into ssh's stdin before any data,
    # which corrupts the tar stream. Use UTF-8 without BOM for the child's stdin.
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)

    $started = Get-Date
    $ssh = [System.Diagnostics.Process]::Start($sshPsi)
    $sshErr = $ssh.StandardError.ReadToEndAsync()
    $tar = [System.Diagnostics.Process]::Start($tarPsi)
    $tarErr = $tar.StandardError.ReadToEndAsync()
    $copy = $tar.StandardOutput.BaseStream.CopyToAsync($ssh.StandardInput.BaseStream, 1MB)
    while (-not $copy.IsCompleted) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 150
    }
    $ssh.StandardInput.Close()   # EOF for the remote tar
    while (-not ($tar.HasExited -and $ssh.HasExited)) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 150
    }
    $elapsed = [int]((Get-Date) - $started).TotalSeconds

    if ($copy.IsFaulted -or $tar.ExitCode -ne 0) {
        $msg = $tarErr.Result.Trim()
        if ($copy.IsFaulted) { $msg += ' ' + $copy.Exception.InnerException.Message }
        Write-Status "Ошибка упаковки на ПК ($name): $msg"
        return $false
    }
    if ($ssh.ExitCode -ne 0) {
        Write-Status "Ошибка на Frame ($name): $($sshErr.Result.Trim())"
        return $false
    }
    $remoteSize = Get-RemoteSize $name
    if ($remoteSize -lt 0) {
        Write-Status "Готово за $elapsed с, но размер на Frame проверить не удалось"
        return $true
    }
    # du counts whole files; directories add a few KB of metadata
    if ([math]::Abs($remoteSize - $localSize) -le 65536 -or $remoteSize -ge $localSize) {
        Write-Status "Готово: $name за $elapsed с, на Frame $(Format-Size $remoteSize)"
        return $true
    }
    Write-Status "Размер не совпал ($name): на ПК $(Format-Size $localSize), на Frame $(Format-Size $remoteSize)"
    return $false
}

$btnSend.Add_Click({
    if ($list.Items.Count -eq 0) { Write-Status 'Сначала добавь файлы или папки'; return }
    Set-Busy $true
    $items = @($list.Items)
    $progress.Maximum = $items.Count
    $progress.Value = 0
    $ok = 0
    foreach ($p in $items) {
        if (Send-Item $p) { $ok++; $list.Items.Remove($p) }
        $progress.Value++
        [System.Windows.Forms.Application]::DoEvents()
    }
    Write-Status "Отправлено: $ok из $($items.Count)"
    Set-Busy $false
})

# Connection check on start
$form.Add_Shown({
    Write-Status "Проверка связи с $Frame…"
    [System.Windows.Forms.Application]::DoEvents()
    & ssh -o BatchMode=yes -o ConnectTimeout=5 $Frame 'true' 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Status 'Frame на связи' }
    else { Write-Status 'Frame недоступен: включён ли шлем и та же ли Wi-Fi сеть?' }
})

[void]$form.ShowDialog()
