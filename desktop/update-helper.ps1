param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$c = $null
$backupComplete = $false
$installStarted = $false
$newProcess = $null
function Write-Stage($message) { Write-Output ((Get-Date).ToString('o') + ' ' + $message) }
function Write-Result($body) { $body | ConvertTo-Json | Set-Content -LiteralPath $c.result -Encoding UTF8 }
function Launch-App {
    $exe = Join-Path $c.target $c.executable
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw ('Application missing: ' + $exe) }
    Start-Process -FilePath $exe -WorkingDirectory $c.target -ArgumentList ("--update-ack=" + $c.token) -PassThru
}
function Check-Cancel {
    if ($c.cancel -and (Test-Path -LiteralPath $c.cancel)) { throw 'Update cancelled before application exit' }
}
try {
    # Windows PowerShell 5.1 otherwise reads UTF-8 JSON as the system ANSI codepage.
    $c = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
    $ack = Join-Path $c.userData ("update-ack-" + $c.token + ".json")
    Write-Stage 'Validating update artifact and installation permissions'
    if ((Get-Item -LiteralPath $c.artifact).Length -ne $c.size -or (Get-FileHash -LiteralPath $c.artifact -Algorithm SHA256).Hash.ToLowerInvariant() -ne $c.sha256) { throw 'Update integrity check failed' }
    if (-not (Test-Path -LiteralPath (Join-Path $c.target $c.executable) -PathType Leaf)) { throw 'Previous application missing' }
    $probe = Join-Path $c.target ('.cleaner-write-' + $c.token)
    $handle = [System.IO.FileStream]::new($probe, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None, 4096, [System.IO.FileOptions]::DeleteOnClose)
    $handle.Dispose()
    Check-Cancel
    if ($c.ready) {
        $readyTemp = $c.ready + '.tmp'
        @{token=$c.token;pid=$PID} | ConvertTo-Json | Set-Content -LiteralPath $readyTemp -Encoding UTF8
        Move-Item -LiteralPath $readyTemp -Destination $c.ready -Force
    }
    Write-Stage 'Helper ready; waiting for previous application to exit'
    $deadline = (Get-Date).AddSeconds(90)
    while (Get-Process -Id $c.pid -ErrorAction SilentlyContinue) {
        Check-Cancel
        if ((Get-Date) -gt $deadline) { throw 'Previous app did not exit' }
        Start-Sleep -Milliseconds 250
    }
    Check-Cancel
    Write-Stage 'Backing up previous application'
    New-Item -ItemType Directory -Path $c.backup -Force | Out-Null
    & robocopy.exe $c.target $c.backup /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -gt 7) { throw ('Cannot back up previous app: ' + $LASTEXITCODE) }
    $backupComplete = $true
    Write-Stage 'Running installer'
    $installStarted = $true
    # NSIS requires /D= to be the final argument, including any spaces in the target.
    $installer = Start-Process -FilePath $c.artifact -ArgumentList ("/S /D=" + $c.target) -Wait -PassThru
    if ($installer.ExitCode -ne 0) { throw ("Installer failed: " + $installer.ExitCode) }
    Write-Stage 'Starting new application'
    $newProcess = Launch-App
    $deadline = (Get-Date).AddSeconds(120)
    $startupReady = $false
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $ack) {
            $r = Get-Content -LiteralPath $ack -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($r.version -eq $c.version -and $r.token -eq $c.token) { $startupReady = $true; break }
        }
        $newProcess.Refresh()
        if ($newProcess.HasExited) { throw ('New application exited before confirming startup: ' + $newProcess.ExitCode) }
        Start-Sleep -Milliseconds 500
    }
    if (-not $startupReady) { throw 'New app did not confirm startup' }
    Write-Result @{status='ok';version=$c.version}
    Write-Stage 'Update completed and new application confirmed startup'
    Remove-Item -LiteralPath $ack -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $c.backup -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    $reason = $_.Exception.Message
    Write-Stage ('Update failed: ' + $reason)
    if (-not $c) { throw }
    if ($newProcess) { Stop-Process -Id $newProcess.Id -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2 }
    if ($installStarted -and $backupComplete) {
        Write-Stage 'Restoring previous application'
        & robocopy.exe $c.backup $c.target /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -gt 7) { $reason += '; previous app restore failed: ' + $LASTEXITCODE }
    }
    @{version=$c.version;sha256=$c.sha256} | ConvertTo-Json | Set-Content -LiteralPath $c.blocked -Encoding UTF8
    Write-Result @{status='failed';version=$c.version;error=$reason;log=$c.helperLog}
    if (-not (Get-Process -Id $c.pid -ErrorAction SilentlyContinue)) {
        try { Launch-App | Out-Null; Write-Stage 'Previous application restarted' } catch { Write-Stage ('Restart failed: ' + $_.Exception.Message) }
    }
}
