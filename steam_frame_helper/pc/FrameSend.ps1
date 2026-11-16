# Frame Send — copies files and folders from this PC to ~/Downloads on the Steam Frame.
# Part of Steam Frame Helper. Uses the SSH key login set up for the Frame and the
# tar/ssh tools built into Windows: tar -c | ssh "tar -x" keeps folders intact and is
# much faster than scp for many small files. The stream is copied by a background thread
# that counts the bytes; tar's verbose list says which file is on its way. After each item
# the size on the Frame is compared with the local one.
# Usage: FrameSend.ps1 [-Send] [paths...]   (paths are added to the list; -Send starts at once)

param(
    [switch]$Send,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Paths
)

$RemoteDir = '~/Downloads'
$TarExe = Join-Path $env:SystemRoot 'System32\tar.exe'
$SshExe = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'

$IsRu = (Get-UICulture).TwoLetterISOLanguageName -eq 'ru'
function T($ru, $en) { if ($IsRu) { $ru } else { $en } }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# dark title bar (Windows 10 20H1+ / 11); ignored where unsupported
Add-Type -Namespace FrameSend -Name Native -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("dwmapi.dll")]
public static extern int DwmSetWindowAttribute(System.IntPtr hwnd, int attr, ref int value, int size);
'@

# Frame address (user@host), written by pc\install.ps1.
$ConfigFile = Join-Path $env:USERPROFILE 'SteamFrameHelper\frame.txt'
$Frame = ''
if (Test-Path -LiteralPath $ConfigFile) {
    $Frame = "$(Get-Content -LiteralPath $ConfigFile -TotalCount 1)".Trim()
}
if (-not $Frame) {
    [System.Windows.Forms.MessageBox]::Show(
        (T "Адрес Steam Frame не задан. Запусти pc\install.ps1 из Steam Frame Helper." "Steam Frame address is not set. Run pc\install.ps1 from Steam Frame Helper."),
        (T 'Отправить на Frame' 'Send to Frame')) | Out-Null
    exit 1
}

# ---------- look (the colours of the headset apps) ----------

function Rgb([int]$hex) { [System.Drawing.Color]::FromArgb(($hex -shr 16) -band 255, ($hex -shr 8) -band 255, $hex -band 255) }
$cWindow = Rgb 0x0b0e14
$cCard = Rgb 0x131822
$cRaised = Rgb 0x1c2230
$cRaisedHot = Rgb 0x283043
$cAccent = Rgb 0x4c9aff
$cAccentHot = Rgb 0x77b3ff
$cText = Rgb 0xeef2f8
$cMuted = Rgb 0x8d97aa
$cGood = Rgb 0x5fd38a
$cBad = Rgb 0xff7b72

$fBody = New-Object System.Drawing.Font('Segoe UI', 10)
$fSmall = New-Object System.Drawing.Font('Segoe UI', 9)
$fTitle = New-Object System.Drawing.Font('Segoe UI Semibold', 15)
$fStrong = New-Object System.Drawing.Font('Segoe UI Semibold', 10.5)
$fBig = New-Object System.Drawing.Font('Segoe UI Semibold', 12)

function Round-Path([System.Drawing.RectangleF]$r, [float]$radius) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = [Math]::Min($radius * 2, [Math]::Min($r.Width, $r.Height))
    if ($d -le 0) { $p.AddRectangle($r); return $p }
    $p.AddArc($r.X, $r.Y, $d, $d, 180, 90)
    $p.AddArc($r.Right - $d, $r.Y, $d, $d, 270, 90)
    $p.AddArc($r.Right - $d, $r.Bottom - $d, $d, $d, 0, 90)
    $p.AddArc($r.X, $r.Bottom - $d, $d, $d, 90, 90)
    $p.CloseFigure()
    return $p
}

function Set-DoubleBuffered($control) {
    $prop = $control.GetType().GetProperty('DoubleBuffered', [System.Reflection.BindingFlags]'Instance,NonPublic')
    $prop.SetValue($control, $true, $null)
}

# small pictures: the window icon (an arrow up, into the headset), a folder, a file
function New-Bitmap([int]$size, [scriptblock]$draw) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    & $draw $g $size
    $g.Dispose()
    return $bmp
}
$iconBitmap = New-Bitmap 64 {
    param($g, $s)
    $g.FillEllipse((New-Object System.Drawing.SolidBrush($cAccent)), 2, 2, $s - 4, $s - 4)
    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 6)
    $pen.StartCap = 'Round'; $pen.EndCap = 'Round'; $pen.LineJoin = 'Round'
    $g.DrawLine($pen, 32, 46, 32, 18)
    $g.DrawLines($pen, [System.Drawing.Point[]]@((New-Object System.Drawing.Point(20, 29)), (New-Object System.Drawing.Point(32, 17)), (New-Object System.Drawing.Point(44, 29))))
}
$folderBitmap = New-Bitmap 22 {
    param($g, $s)
    $b = New-Object System.Drawing.SolidBrush($cAccent)
    $g.FillPath($b, (Round-Path (New-Object System.Drawing.RectangleF(2, 4, 9, 5)) 1.5))
    $g.FillPath($b, (Round-Path (New-Object System.Drawing.RectangleF(2, 6, 18, 12)) 2))
}
$fileBitmap = New-Bitmap 22 {
    param($g, $s)
    $pen = New-Object System.Drawing.Pen($cMuted, 1.6)
    $g.DrawPath($pen, (Round-Path (New-Object System.Drawing.RectangleF(5, 2.5, 12, 17)) 2))
    $g.DrawLine($pen, 8, 9, 14, 9); $g.DrawLine($pen, 8, 12.5, 14, 12.5); $g.DrawLine($pen, 8, 16, 12, 16)
}

# ---------- helpers ----------

# what tar will pack for one item: payload bytes, files, folders (relative names, for the verbose list),
# and the tar stream's size (a 512-byte header per entry, data in 512-byte blocks, the end blocks)
function Measure-Item([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    $info = @{ Bytes = [int64]0; Files = 0; Stream = [int64]0; Dirs = New-Object 'System.Collections.Generic.HashSet[string]' }
    $add = {
        param([int64]$len)
        $info.Bytes += $len
        $info.Files++
        $info.Stream += 512 + [int64]([Math]::Ceiling($len / 512.0) * 512)
    }
    if (-not $item.PSIsContainer) {
        & $add $item.Length
    } else {
        $base = [System.IO.Path]::GetDirectoryName($item.FullName.TrimEnd('\'))
        [void]$info.Dirs.Add($item.Name.ToLowerInvariant())
        $info.Stream += 512
        foreach ($e in Get-ChildItem -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue) {
            if ($e.PSIsContainer) {
                [void]$info.Dirs.Add($e.FullName.Substring($base.Length).TrimStart('\').ToLowerInvariant())
                $info.Stream += 512
            } else {
                & $add $e.Length
            }
        }
    }
    $info.Stream += 10240   # the end of the archive, padded to a record
    return $info
}

function Format-Size([int64]$Bytes) {
    if ($Bytes -ge 1GB) { return ('{0:N2} ' + (T 'ГБ' 'GB')) -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return ('{0:N1} ' + (T 'МБ' 'MB')) -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return ('{0:N0} ' + (T 'КБ' 'KB')) -f ($Bytes / 1KB) }
    return "$Bytes " + (T 'Б' 'B')
}

function Format-Time([double]$Seconds) {
    if ($Seconds -lt 0 -or [double]::IsInfinity($Seconds) -or [double]::IsNaN($Seconds)) { return '—' }
    $s = [int][Math]::Ceiling($Seconds)
    if ($s -ge 3600) { return (T '{0} ч {1:00} мин' '{0} h {1:00} min') -f [int][Math]::Floor($s / 3600), [int][Math]::Floor(($s % 3600) / 60) }
    if ($s -ge 60) { return (T '{0} мин {1:00} с' '{0} min {1:00} s') -f [int][Math]::Floor($s / 60), ($s % 60) }
    return (T '{0} с' '{0} s') -f $s
}

function Quote-Remote([string]$Name) {
    # single-quote for the remote POSIX shell
    return "'" + $Name.Replace("'", "'\''") + "'"
}

function Get-RemoteSize([string]$Name) {
    $q = Quote-Remote $Name
    $out = & $SshExe -o BatchMode=yes -o ConnectTimeout=5 $Frame "du -sb --apparent-size $RemoteDir/$q 2>/dev/null | cut -f1"
    if ($LASTEXITCODE -eq 0 -and "$out".Trim() -match '^\d+$') { return [int64]"$out".Trim() }
    return [int64]-1
}

# ---------- window ----------

$form = New-Object System.Windows.Forms.Form
$form.Text = T 'Отправка на Steam Frame' 'Send to Steam Frame'
$form.ClientSize = New-Object System.Drawing.Size(720, 600)
$form.MinimumSize = New-Object System.Drawing.Size(600, 520)
$form.StartPosition = 'CenterScreen'
$form.AllowDrop = $true
$form.BackColor = $cWindow
$form.ForeColor = $cText
$form.Font = $fBody
$form.Icon = [System.Drawing.Icon]::FromHandle($iconBitmap.GetHicon())
$form.Padding = New-Object System.Windows.Forms.Padding(18, 14, 18, 16)
$form.Add_HandleCreated({
    $on = 1
    [void][FrameSend.Native]::DwmSetWindowAttribute($form.Handle, 20, [ref]$on, 4)
})

# header: title, where the files go, the connection
$header = New-Object System.Windows.Forms.Panel
$header.Dock = 'Top'
$header.Height = 66
$title = New-Object System.Windows.Forms.Label
$title.Text = T 'Отправка на Steam Frame' 'Send to Steam Frame'
$title.Font = $fTitle
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(0, 0)
$where = New-Object System.Windows.Forms.Label
$where.Text = (T 'Куда: ' 'To: ') + "$Frame  →  $RemoteDir"
$where.ForeColor = $cMuted
$where.AutoSize = $true
$where.Location = New-Object System.Drawing.Point(2, 36)
$conn = New-Object System.Windows.Forms.Label
$conn.Text = T '●  проверка связи…' '●  checking…'
$conn.ForeColor = $cMuted
$conn.AutoSize = $true
$conn.Anchor = 'Top, Right'
$header.Controls.AddRange(@($title, $where, $conn))
$header.Add_Resize({ $conn.Location = New-Object System.Drawing.Point(($header.Width - $conn.Width), 8) })

# a card: a rounded panel
function New-Card {
    $p = New-Object System.Windows.Forms.Panel
    $p.BackColor = $cWindow
    $p.Padding = New-Object System.Windows.Forms.Padding(14, 12, 14, 12)
    Set-DoubleBuffered $p
    $p.Add_Paint({
        param($s, $e)
        $e.Graphics.SmoothingMode = 'AntiAlias'
        $r = New-Object System.Drawing.RectangleF(0, 0, ($s.Width - 1), ($s.Height - 1))
        $e.Graphics.FillPath((New-Object System.Drawing.SolidBrush($cCard)), (Round-Path $r 14))
    })
    $p.Add_Resize({ param($s, $e) $s.Invalidate() })
    return $p
}

# the list of what to send
$listCard = New-Card
$listCard.Dock = 'Fill'
$list = New-Object System.Windows.Forms.ListView
$list.View = 'Details'
$list.HeaderStyle = 'None'
$list.FullRowSelect = $true
$list.BorderStyle = 'None'
$list.BackColor = $cCard
$list.ForeColor = $cText
$list.Font = $fBody
$list.Dock = 'Fill'
$list.AllowDrop = $true
$list.MultiSelect = $true
$images = New-Object System.Windows.Forms.ImageList
$images.ImageSize = New-Object System.Drawing.Size(22, 22)
$images.ColorDepth = 'Depth32Bit'
$images.Images.Add('folder', $folderBitmap)
$images.Images.Add('file', $fileBitmap)
$list.SmallImageList = $images
[void]$list.Columns.Add('name', 300)
[void]$list.Columns.Add('size', 110, 'Right')
[void]$list.Columns.Add('state', 150, 'Right')
function Set-Columns {
    $list.Columns[1].Width = 200   # size; folders: and the number of files
    $list.Columns[2].Width = 140
    $list.Columns[0].Width = [Math]::Max(120, $list.ClientSize.Width - 344)
}
$list.Add_Resize({ Set-Columns })
$hint = New-Object System.Windows.Forms.Label
$hint.Text = T "Перетащите сюда файлы или папки`nили нажмите «Добавить файлы» / «Добавить папку»" "Drop files or folders here`nor press «Add files» / «Add folder»"
$hint.ForeColor = $cMuted
$hint.BackColor = $cCard
$hint.TextAlign = 'MiddleCenter'
$hint.Dock = 'Fill'
$hint.AllowDrop = $true
$listCard.Controls.Add($hint)
$listCard.Controls.Add($list)

# the transfer: what goes now, the bar, the numbers
$progCard = New-Card
$progCard.Dock = 'Bottom'
$progCard.Height = 150
$progCard.Visible = $false
$nowLabel = New-Object System.Windows.Forms.Label
$nowLabel.Font = $fStrong
$nowLabel.AutoEllipsis = $true
$nowLabel.BackColor = $cCard
$nowLabel.Location = New-Object System.Drawing.Point(16, 12)
$nowLabel.Anchor = 'Top, Left, Right'
$fileLabel = New-Object System.Windows.Forms.Label
$fileLabel.ForeColor = $cMuted
$fileLabel.Font = $fSmall
$fileLabel.AutoEllipsis = $true
$fileLabel.BackColor = $cCard
$fileLabel.Location = New-Object System.Drawing.Point(16, 36)
$fileLabel.Anchor = 'Top, Left, Right'
$bar = New-Object System.Windows.Forms.Panel
$bar.BackColor = $cCard
$bar.Location = New-Object System.Drawing.Point(16, 62)
$bar.Height = 12
$bar.Anchor = 'Top, Left, Right'
$bar.Tag = [double]0
Set-DoubleBuffered $bar
$bar.Add_Paint({
    param($s, $e)
    $g = $e.Graphics
    $g.SmoothingMode = 'AntiAlias'
    $r = New-Object System.Drawing.RectangleF(0, 0, ($s.Width - 1), ($s.Height - 1))
    $g.FillPath((New-Object System.Drawing.SolidBrush($cRaised)), (Round-Path $r 6))
    $frac = [Math]::Max(0.0, [Math]::Min(1.0, [double]$s.Tag))
    if ($frac -gt 0) {
        $fw = [Math]::Max($r.Height, $r.Width * $frac)
        $fr = New-Object System.Drawing.RectangleF(0, 0, $fw, $r.Height)
        $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($fr, $cAccent, $cAccentHot, [System.Drawing.Drawing2D.LinearGradientMode]::Horizontal)
        $g.FillPath($brush, (Round-Path $fr 6))
    }
})
$percentLabel = New-Object System.Windows.Forms.Label
$percentLabel.Font = $fBig
$percentLabel.BackColor = $cCard
$percentLabel.AutoSize = $true
$percentLabel.Location = New-Object System.Drawing.Point(14, 84)
$amountLabel = New-Object System.Windows.Forms.Label
$amountLabel.ForeColor = $cMuted
$amountLabel.BackColor = $cCard
$amountLabel.AutoSize = $true
$amountLabel.Location = New-Object System.Drawing.Point(16, 112)
$speedLabel = New-Object System.Windows.Forms.Label
$speedLabel.Font = $fBig
$speedLabel.BackColor = $cCard
$speedLabel.AutoSize = $true
$speedLabel.Anchor = 'Top, Right'
$leftLabel = New-Object System.Windows.Forms.Label
$leftLabel.ForeColor = $cMuted
$leftLabel.BackColor = $cCard
$leftLabel.AutoSize = $true
$leftLabel.Anchor = 'Top, Right'
$progCard.Controls.AddRange(@($nowLabel, $fileLabel, $bar, $percentLabel, $amountLabel, $speedLabel, $leftLabel))
$progCard.Add_Resize({
    $w = $progCard.Width - 32
    $nowLabel.Width = $w; $fileLabel.Width = $w; $bar.Width = $w
    $speedLabel.Location = New-Object System.Drawing.Point(($progCard.Width - 16 - $speedLabel.Width), 84)
    $leftLabel.Location = New-Object System.Drawing.Point(($progCard.Width - 16 - $leftLabel.Width), 112)
})

# buttons
$buttons = New-Object System.Windows.Forms.Panel
$buttons.Dock = 'Bottom'
$buttons.Height = 58
function New-Button([string]$Text, [bool]$Accent) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $Text
    $b.FlatStyle = 'Flat'
    $b.FlatAppearance.BorderSize = 0
    $b.Height = 40
    $b.Font = if ($Accent) { $fStrong } else { $fBody }
    $b.ForeColor = if ($Accent) { [System.Drawing.Color]::White } else { $cText }
    $b.BackColor = if ($Accent) { $cAccent } else { $cRaised }
    $b.FlatAppearance.MouseOverBackColor = if ($Accent) { $cAccentHot } else { $cRaisedHot }
    $b.FlatAppearance.MouseDownBackColor = if ($Accent) { $cAccentHot } else { $cRaisedHot }
    $b.Cursor = 'Hand'
    $size = [System.Windows.Forms.TextRenderer]::MeasureText($Text, $b.Font)
    $b.Width = $size.Width + 36
    $buttons.Controls.Add($b)
    return $b
}
$btnFiles = New-Button (T 'Добавить файлы' 'Add files') $false
$btnFolder = New-Button (T 'Добавить папку' 'Add folder') $false
$btnRemove = New-Button (T 'Убрать' 'Remove') $false
$btnSend = New-Button (T 'Отправить' 'Send') $true
$btnSend.Width = [Math]::Max($btnSend.Width, ([System.Windows.Forms.TextRenderer]::MeasureText((T 'Отменить' 'Cancel'), $fStrong).Width + 48))
$buttons.Add_Resize({
    $x = 0
    foreach ($b in @($btnFiles, $btnFolder, $btnRemove)) { $b.Location = New-Object System.Drawing.Point($x, 14); $x += $b.Width + 8 }
    $btnSend.Location = New-Object System.Drawing.Point(($buttons.Width - $btnSend.Width), 14)
})

# messages: one line, the newest (the full list stays in the tooltip)
$status = New-Object System.Windows.Forms.Label
$status.Dock = 'Bottom'
$status.Height = 26
$status.ForeColor = $cMuted
$status.Font = $fSmall
$status.AutoEllipsis = $true
$status.TextAlign = 'BottomLeft'
$tips = New-Object System.Windows.Forms.ToolTip
$log = New-Object System.Text.StringBuilder

$spacer = New-Object System.Windows.Forms.Panel
$spacer.Dock = 'Bottom'
$spacer.Height = 12

$gap = New-Object System.Windows.Forms.Panel
$gap.Dock = 'Top'
$gap.Height = 10

# docking order: the last added is placed first
$form.Controls.Add($listCard)
$form.Controls.Add($gap)
$form.Controls.Add($header)
$form.Controls.Add($spacer)
$form.Controls.Add($progCard)
$form.Controls.Add($buttons)
$form.Controls.Add($status)

function Write-Status([string]$Text, $Color = $null) {
    $line = '{0:HH:mm:ss}  {1}' -f (Get-Date), $Text
    [void]$log.AppendLine($line)
    $status.Text = $Text
    $status.ForeColor = if ($Color) { $Color } else { $cMuted }
    $tips.SetToolTip($status, $log.ToString().TrimEnd())
}

# ---------- the list ----------

$items = New-Object System.Collections.ArrayList   # @{ Path; Name; Info; Row }

function Update-Hint { $hint.Visible = $list.Items.Count -eq 0; $list.Visible = -not $hint.Visible }

function Add-Paths([string[]]$Paths) {
    $form.Cursor = 'WaitCursor'
    foreach ($p in $Paths) {
        if (-not $p -or -not (Test-Path -LiteralPath $p)) { continue }
        $full = (Get-Item -LiteralPath $p -Force).FullName
        if (@($items | Where-Object { $_.Path -eq $full }).Count) { continue }
        $item = Get-Item -LiteralPath $full -Force
        $info = Measure-Item $full
        $row = New-Object System.Windows.Forms.ListViewItem($item.Name)
        $row.ImageKey = if ($item.PSIsContainer) { 'folder' } else { 'file' }
        $sizeText = Format-Size $info.Bytes
        if ($item.PSIsContainer) { $sizeText = (T '{0} · {1} файл.' '{0} · {1} files') -f $sizeText, $info.Files }
        [void]$row.SubItems.Add($sizeText)
        [void]$row.SubItems.Add((T 'ждёт' 'waiting'))
        $row.UseItemStyleForSubItems = $false
        $row.SubItems[1].ForeColor = $cMuted
        $row.SubItems[2].ForeColor = $cMuted
        $row.ToolTipText = $full
        [void]$list.Items.Add($row)
        [void]$items.Add(@{ Path = $full; Name = $item.Name; Info = $info; Row = $row })
    }
    $list.ShowItemToolTips = $true
    $form.Cursor = 'Default'
    Update-Hint
    Set-Columns
}

function Set-RowState($entry, [string]$Text, $Color) {
    $entry.Row.SubItems[2].Text = $Text
    $entry.Row.SubItems[2].ForeColor = $Color
}

$btnFiles.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Multiselect = $true
    $dlg.Title = T 'Файлы для отправки на Frame' 'Files to send to the Frame'
    if ($dlg.ShowDialog($form) -eq 'OK') { Add-Paths $dlg.FileNames }
})
$btnFolder.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = T 'Папка для отправки на Frame' 'Folder to send to the Frame'
    if ($dlg.ShowDialog($form) -eq 'OK') { Add-Paths @($dlg.SelectedPath) }
})
$btnRemove.Add_Click({
    foreach ($row in @($list.SelectedItems)) {
        $entry = $items | Where-Object { $_.Row -eq $row } | Select-Object -First 1
        if ($entry) { $items.Remove($entry) }
        $list.Items.Remove($row)
    }
    Update-Hint
})
$list.Add_KeyDown({ param($s, $e) if ($e.KeyCode -eq 'Delete' -and $btnRemove.Enabled) { $btnRemove.PerformClick() } })

$onDragEnter = {
    param($s, $e)
    if ($btnFiles.Enabled -and $e.Data.GetDataPresent([System.Windows.Forms.DataFormats]::FileDrop)) { $e.Effect = 'Copy' }
}
$onDragDrop = {
    param($s, $e)
    Add-Paths ([string[]]$e.Data.GetData([System.Windows.Forms.DataFormats]::FileDrop))
}
foreach ($c in @($form, $list, $hint, $listCard)) { $c.Add_DragEnter($onDragEnter); $c.Add_DragDrop($onDragDrop) }
$hint.Add_Click({ if ($btnFiles.Enabled) { $btnFiles.PerformClick() } })

# ---------- sending ----------

$script:busy = $false
$script:cancel = $false
$script:procs = @()

function Set-Busy([bool]$Busy) {
    $script:busy = $Busy
    foreach ($b in @($btnFiles, $btnFolder, $btnRemove)) { $b.Enabled = -not $Busy }
    $btnSend.Text = if ($Busy) { T 'Отменить' 'Cancel' } else { T 'Отправить' 'Send' }
    $btnSend.BackColor = if ($Busy) { $cRaised } else { $cAccent }
    $btnSend.FlatAppearance.MouseOverBackColor = if ($Busy) { $cRaisedHot } else { $cAccentHot }
    # no blue selected row left in the list (the states are coloured)
    $list.SelectedItems.Clear()
    $form.ActiveControl = $btnSend
}

# the background copy: tar's output into ssh's input, counting; and tar's list of files
$copyScript = {
    param($src, $dst, $sync)
    $buf = New-Object byte[] (1MB)
    try {
        while (-not $sync.Cancel) {
            $n = $src.Read($buf, 0, $buf.Length)
            if ($n -le 0) { break }
            $dst.Write($buf, 0, $n)
            $sync.Bytes += $n
        }
        $dst.Flush()
    } catch {
        if (-not $sync.Cancel) { $sync.CopyError = $_.Exception.Message }
    } finally {
        try { $dst.Close() } catch { }   # EOF for the remote tar
        $sync.CopyDone = $true
    }
}
$listScript = {
    param($reader, $sync, $dirs)
    # tar prints "a <name>" when it starts an entry and the line's end only when the entry is
    # written: read by characters, so the file on its way is known while it is sent
    $line = New-Object System.Text.StringBuilder
    while (($c = $reader.Read()) -ge 0) {
        $ch = [char]$c
        if ($ch -eq "`r") { continue }
        if ($ch -ne "`n") {
            [void]$line.Append($ch)
            if ($line.Length -gt 2 -and $line[0] -eq 'a' -and $line[1] -eq ' ') { $sync.Current = $line.ToString(2, $line.Length - 2) }
            continue
        }
        $text = $line.ToString()
        [void]$line.Clear()
        if ($text.StartsWith('a ')) {
            # folders are listed too: only files are counted
            if (-not $dirs.Contains($text.Substring(2).Replace('/', '\').TrimEnd('\').ToLowerInvariant())) { $sync.Files++ }
        } elseif ($text) {
            [void]$sync.TarErrors.AppendLine($text)
        }
    }
    $sync.ListDone = $true
}

function Start-Thread([scriptblock]$Code, [object[]]$Arguments) {
    $ps = [PowerShell]::Create()
    [void]$ps.AddScript($Code)
    foreach ($a in $Arguments) { [void]$ps.AddArgument($a) }
    return @{ PS = $ps; Handle = $ps.BeginInvoke() }
}

$script:total = @{ Stream = [int64]0; Bytes = [int64]0; Files = 0; Count = 0 }
$script:doneBefore = @{ Stream = [int64]0; Files = 0 }
$script:samples = New-Object System.Collections.Generic.Queue[object]

function Update-Progress($entry, $sync, [int]$index) {
    $info = $entry.Info
    $streamNow = $script:doneBefore.Stream + [Math]::Min([int64]$sync.Bytes, $info.Stream)
    $frac = if ($script:total.Stream -gt 0) { $streamNow / $script:total.Stream } else { 0 }
    $frac = [Math]::Min($frac, 0.999)
    $bytesNow = [int64]($script:total.Bytes * $frac)

    # speed over the last 3 seconds
    $now = [DateTime]::UtcNow
    $script:samples.Enqueue(@($now, $streamNow))
    while ($script:samples.Count -gt 1 -and ($now - $script:samples.Peek()[0]).TotalSeconds -gt 3) { [void]$script:samples.Dequeue() }
    $first = $script:samples.Peek()
    $dt = ($now - $first[0]).TotalSeconds
    $speed = if ($dt -gt 0.4) { ($streamNow - $first[1]) / $dt } else { 0 }

    $bar.Tag = [double]$frac
    $bar.Invalidate()
    $percentLabel.Text = '{0:0}%' -f ($frac * 100)
    $amountLabel.Text = (T '{0} из {1}' '{0} of {1}') -f (Format-Size $bytesNow), (Format-Size $script:total.Bytes)
    if ($speed -gt 0) {
        $speedLabel.Text = (Format-Size ([int64]$speed)) + (T '/с' '/s')
        $leftLabel.Text = (T 'осталось ' 'left ') + (Format-Time (($script:total.Stream - $streamNow) / $speed))
    } else {
        $speedLabel.Text = '…'
        $leftLabel.Text = T 'оцениваю время…' 'estimating…'
    }

    $head = if ($script:total.Count -gt 1) { (T '{0} из {1}: ' '{0} of {1}: ') -f $index, $script:total.Count } else { '' }
    $nowLabel.Text = $head + $entry.Name
    $current = "$($sync.Current)"
    if ($info.Dirs.Count -gt 0) {
        # the files written so far, plus the one on its way; the name without the folder sent
        $filesNow = [Math]::Min([int]$sync.Files + 1, $info.Files)
        $shown = $current
        if ($shown.StartsWith($entry.Name + '/')) { $shown = $shown.Substring($entry.Name.Length + 1) }
        $fileLabel.Text = (T 'Файл {0} из {1}:  {2}' 'File {0} of {1}:  {2}') -f $filesNow, $info.Files, $shown
    } else {
        $fileLabel.Text = Format-Size $info.Bytes
    }
    $progCard.PerformLayout()
    $speedLabel.Location = New-Object System.Drawing.Point(($progCard.Width - 16 - $speedLabel.Width), 84)
    $leftLabel.Location = New-Object System.Drawing.Point(($progCard.Width - 16 - $leftLabel.Width), 112)
}

function Send-Item($entry, [int]$index) {
    $item = Get-Item -LiteralPath $entry.Path -Force
    # (Split-Path -LiteralPath ... -Parent is an invalid parameter set in PowerShell 5.1)
    $parent = [System.IO.Path]::GetDirectoryName($item.FullName.TrimEnd('\'))
    $name = $item.Name
    Set-RowState $entry (T 'отправляется…' 'sending…') $cAccentHot

    # tar.exe stdout is copied into ssh.exe stdin by .NET streams: no cmd.exe in between
    # (cmd parses %, ^, & in file names), and PowerShell 5.1 pipes between native
    # programs are not binary-safe. -v lists each entry on stderr ("a <name>").
    $tarPsi = New-Object System.Diagnostics.ProcessStartInfo
    $tarPsi.FileName = $TarExe
    $tarPsi.Arguments = "-cvf - -C `"$parent`" `"$name`""
    $tarPsi.UseShellExecute = $false
    $tarPsi.CreateNoWindow = $true
    $tarPsi.RedirectStandardOutput = $true
    $tarPsi.RedirectStandardError = $true
    # tar.exe writes its list in the ANSI code page (1251 on Russian Windows), not UTF-8
    $tarPsi.StandardErrorEncoding = [System.Text.Encoding]::GetEncoding([System.Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage)

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

    $sync = [hashtable]::Synchronized(@{
        Bytes = [int64]0; Cancel = $false; CopyDone = $false; CopyError = ''; ListDone = $false
        Current = ''; Files = 0; TarErrors = (New-Object System.Text.StringBuilder)
    })
    $started = Get-Date
    $ssh = [System.Diagnostics.Process]::Start($sshPsi)
    $sshErr = $ssh.StandardError.ReadToEndAsync()
    $tar = [System.Diagnostics.Process]::Start($tarPsi)
    $script:procs = @($tar, $ssh)
    $copy = Start-Thread $copyScript @($tar.StandardOutput.BaseStream, $ssh.StandardInput.BaseStream, $sync)
    $lister = Start-Thread $listScript @($tar.StandardError, $sync, $entry.Info.Dirs)

    while (-not ($sync.CopyDone -and $tar.HasExited -and $ssh.HasExited)) {
        if ($script:cancel -and -not $sync.Cancel) {
            $sync.Cancel = $true
            foreach ($p in @($tar, $ssh)) { try { if (-not $p.HasExited) { $p.Kill() } } catch { } }
        }
        Update-Progress $entry $sync $index
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 60
    }
    $copy.PS.EndInvoke($copy.Handle); $copy.PS.Dispose()
    $deadline = (Get-Date).AddSeconds(2)
    while (-not $sync.ListDone -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 20 }
    $lister.PS.Dispose()
    $script:procs = @()
    $elapsed = ((Get-Date) - $started).TotalSeconds
    $script:doneBefore.Stream += $entry.Info.Stream

    if ($script:cancel) {
        Set-RowState $entry (T 'отменено' 'cancelled') $cMuted
        return $false
    }
    if ($sync.CopyError -or $tar.ExitCode -ne 0) {
        $msg = ("$($sync.TarErrors)".Trim() + ' ' + $sync.CopyError).Trim()
        Write-Status ((T 'Ошибка упаковки на ПК ({0}): {1}' 'Packing error on the PC ({0}): {1}') -f $name, $msg) $cBad
        Set-RowState $entry (T 'ошибка' 'error') $cBad
        return $false
    }
    if ($ssh.ExitCode -ne 0) {
        Write-Status ((T 'Ошибка на Frame ({0}): {1}' 'Error on the Frame ({0}): {1}') -f $name, $sshErr.Result.Trim()) $cBad
        Set-RowState $entry (T 'ошибка' 'error') $cBad
        return $false
    }
    Set-RowState $entry (T 'проверка…' 'checking…') $cMuted
    [System.Windows.Forms.Application]::DoEvents()
    $remoteSize = Get-RemoteSize $name
    $avg = if ($elapsed -gt 0) { (Format-Size ([int64]($entry.Info.Stream / $elapsed))) + (T '/с' '/s') } else { '' }
    if ($remoteSize -lt 0) {
        Write-Status ((T 'Готово: {0} за {1} ({2}), размер на Frame проверить не удалось' 'Done: {0} in {1} ({2}), could not check the size on the Frame') -f $name, (Format-Time $elapsed), $avg)
        Set-RowState $entry (T 'отправлено' 'sent') $cGood
        return $true
    }
    # du counts whole files; directories add a few KB of metadata
    if ([math]::Abs($remoteSize - $entry.Info.Bytes) -le 65536 -or $remoteSize -ge $entry.Info.Bytes) {
        Write-Status ((T 'Готово: {0} за {1}, в среднем {2}' 'Done: {0} in {1}, {2} on average') -f $name, (Format-Time $elapsed), $avg) $cGood
        Set-RowState $entry (T '✓ на Frame' '✓ on the Frame') $cGood
        return $true
    }
    Write-Status ((T 'Размер не совпал ({0}): на ПК {1}, на Frame {2}' 'Size mismatch ({0}): PC {1}, Frame {2}') -f $name, (Format-Size $entry.Info.Bytes), (Format-Size $remoteSize)) $cBad
    Set-RowState $entry (T 'размер не совпал' 'size mismatch') $cBad
    return $false
}

$btnSend.Add_Click({
    if ($script:busy) {   # "Cancel"
        $script:cancel = $true
        $btnSend.Enabled = $false
        return
    }
    $pending = @($items | Where-Object { $_.Row.SubItems[2].ForeColor -ne $cGood })
    if ($pending.Count -eq 0) {
        Write-Status (T 'Сначала добавьте файлы или папки' 'Add files or folders first')
        return
    }
    Set-Busy $true
    $script:cancel = $false
    $script:total = @{ Stream = [int64]0; Bytes = [int64]0; Files = 0; Count = $pending.Count }
    foreach ($e in $pending) { $script:total.Stream += $e.Info.Stream; $script:total.Bytes += $e.Info.Bytes; $script:total.Files += $e.Info.Files }
    $script:doneBefore = @{ Stream = [int64]0; Files = 0 }
    $script:samples.Clear()
    $progCard.Visible = $true
    $started = Get-Date
    $ok = 0
    $index = 0
    foreach ($e in $pending) {
        $index++
        if ($script:cancel) { break }
        if (Send-Item $e $index) { $ok++ }
        [System.Windows.Forms.Application]::DoEvents()
    }
    $elapsed = ((Get-Date) - $started).TotalSeconds
    if ($script:cancel) {
        $nowLabel.Text = T 'Отменено' 'Cancelled'
        $fileLabel.Text = T 'Уже переданная часть осталась в ~/Downloads на Frame.' 'What was already sent stays in ~/Downloads on the Frame.'
        $speedLabel.Text = ''
        $leftLabel.Text = ''
        Write-Status ((T 'Отменено. Отправлено полностью: {0} из {1}' 'Cancelled. Sent completely: {0} of {1}') -f $ok, $pending.Count)
    } else {
        if ($ok -eq $pending.Count) {
            $bar.Tag = [double]1; $bar.Invalidate()
            $percentLabel.Text = '100%'
            $amountLabel.Text = Format-Size $script:total.Bytes
            $nowLabel.Text = T 'Всё отправлено' 'All sent'
            $fileLabel.Text = (T 'Лежит в ~/Downloads на Frame' 'In ~/Downloads on the Frame')
        } else {
            $nowLabel.Text = (T 'Отправлено {0} из {1}' 'Sent {0} of {1}') -f $ok, $pending.Count
            $fileLabel.Text = T 'Что не получилось, отмечено в списке; наведите на строку внизу, чтобы увидеть все сообщения.' 'What failed is marked in the list; hover the line at the bottom to see all messages.'
        }
        $speedLabel.Text = if ($elapsed -gt 0) { (Format-Size ([int64]($script:total.Stream / $elapsed))) + (T '/с' '/s') } else { '' }
        $leftLabel.Text = (T 'за ' 'in ') + (Format-Time $elapsed)
        $progCard.PerformLayout()
        $speedLabel.Location = New-Object System.Drawing.Point(($progCard.Width - 16 - $speedLabel.Width), 84)
        $leftLabel.Location = New-Object System.Drawing.Point(($progCard.Width - 16 - $leftLabel.Width), 112)
    }
    $btnSend.Enabled = $true
    Set-Busy $false
})

# closing while sending: stop the transfer first
$form.Add_FormClosing({
    param($s, $e)
    if ($script:busy) {
        $answer = [System.Windows.Forms.MessageBox]::Show($form,
            (T 'Отправка ещё идёт. Прервать и закрыть?' 'Still sending. Stop and close?'),
            (T 'Отправка на Steam Frame' 'Send to Steam Frame'), 'YesNo', 'Question')
        if ($answer -ne 'Yes') { $e.Cancel = $true; return }
        $script:cancel = $true
        foreach ($p in $script:procs) { try { if (-not $p.HasExited) { $p.Kill() } } catch { } }
    }
})

# connection check on start
$form.Add_Shown({
    Update-Hint
    $buttons.PerformLayout()
    [System.Windows.Forms.Application]::DoEvents()
    & $SshExe -o BatchMode=yes -o ConnectTimeout=5 $Frame 'true' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $conn.Text = T '●  Frame на связи' '●  Frame is reachable'
        $conn.ForeColor = $cGood
    } else {
        $conn.Text = T '●  Frame недоступен' '●  Frame is unreachable'
        $conn.ForeColor = $cBad
        Write-Status (T 'Frame недоступен: включён ли шлем и та же ли Wi-Fi сеть?' 'Frame is unreachable. Is the headset on and on the same Wi-Fi network?') $cBad
    }
    $conn.Location = New-Object System.Drawing.Point(($header.Width - $conn.Width), 8)
    if ($Paths) { Add-Paths $Paths }
    if ($Send -and $items.Count -gt 0 -and $LASTEXITCODE -eq 0) { $btnSend.PerformClick() }
})

[void]$form.ShowDialog()
