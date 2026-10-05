param(
  [string]$WebPath = "",
  [int]$CdpPort = 0,
  [switch]$NoPush,
  [switch]$KeepPgAdmin
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Find-WebPath {
  param([string]$Explicit)
  if ($Explicit) { return (Resolve-Path $Explicit).Path }
  $candidates = @(
    "$env:ProgramFiles\pgAdmin 4\web",
    "$env:LOCALAPPDATA\Programs\pgAdmin 4\web"
  )
  if ($env:ProgramFiles) {
    $candidates += Get-ChildItem "$env:ProgramFiles\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
      ForEach-Object { Join-Path $_.FullName 'pgAdmin 4\web' }
  }
  $found = @($candidates | Where-Object { $_ -and (Test-Path (Join-Path $_ 'config.py')) })
  if ($found.Count -eq 1) { return (Resolve-Path $found[0]).Path }
  if ($found.Count -eq 0) { throw 'pgAdmin web directory not found. Re-run with -WebPath "C:\...\pgAdmin 4\web".' }
  throw "Multiple pgAdmin installations found:`n$($found -join "`n")`nRe-run with -WebPath."
}

function Find-PgAdminExe([string]$Web) {
  $base = Split-Path $Web -Parent
  $candidates = @(
    (Join-Path $base 'runtime\pgAdmin4.exe'),
    (Join-Path $base 'pgAdmin4.exe'),
    "$env:ProgramFiles\pgAdmin 4\runtime\pgAdmin4.exe",
    "$env:LOCALAPPDATA\Programs\pgAdmin 4\runtime\pgAdmin4.exe"
  )
  foreach ($p in $candidates) {
    if ($p -and (Test-Path $p)) { return (Resolve-Path $p).Path }
  }
  throw 'pgAdmin4.exe not found next to the detected web directory.'
}

function Get-FreeTcpPort {
  $listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback, 0
  )
  try {
    $listener.Start()
    return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
  } finally {
    $listener.Stop()
  }
}

function Test-TcpPortAvailable([int]$Port) {
  if ($Port -le 0) { return $false }
  $listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback, $Port
  )
  try {
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    try { $listener.Stop() } catch {}
  }
}

$WebPath = Find-WebPath $WebPath
$PgAdminExe = Find-PgAdminExe $WebPath
Write-Host "pgAdmin web: $WebPath"
Write-Host "pgAdmin exe: $PgAdminExe"

# Clean screenshots/report from the previous run.
$Artifacts = Join-Path $Root 'artifacts'
$Screens = Join-Path $Artifacts 'screenshots'
New-Item -ItemType Directory -Force -Path $Screens | Out-Null
Get-ChildItem $Screens -File -ErrorAction SilentlyContinue | Remove-Item -Force
Remove-Item (Join-Path $Artifacts 'e2e-report.json') -Force -ErrorAction SilentlyContinue

# Keep Python dependencies isolated from the user's global Python installation.
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
  Write-Host 'Creating local Python virtual environment...'
  python -m venv $Venv
}
& $VenvPython -m pip install --disable-pip-version-check -q Babel==2.18.0 Jinja2 playwright

# Static/local QA first.
& $VenvPython .\qa_translation.py
if ($LASTEXITCODE -ne 0) { throw 'qa_translation.py failed.' }
& $VenvPython .\verify_keyset.py
if ($LASTEXITCODE -ne 0) { throw 'verify_keyset.py failed.' }
& $VenvPython .\verify_rtl.py
if ($LASTEXITCODE -ne 0) { throw 'verify_rtl.py failed.' }

if (Test-Path .\messages-v9.18.pot) {
  & $VenvPython .\verify_upstream.py .\messages-v9.18.pot
  if ($LASTEXITCODE -ne 0) { throw 'verify_upstream.py failed.' }
} else {
  Write-Host 'Upstream POT file not present; offline REL-9_18 key-set fingerprint already verified.'
}

# Install Hebrew + RTL into the detected pgAdmin 9.18 tree.
powershell -ExecutionPolicy Bypass -File .\install-hebrew.ps1 -WebPath $WebPath
if ($LASTEXITCODE -ne 0) { throw 'Hebrew installation failed.' }

# A clean Electron launch is required for DevTools/CDP attachment.
$running = Get-Process pgAdmin4 -ErrorAction SilentlyContinue
if ($running) {
  Write-Host 'Closing running pgAdmin4 processes for the UI test...'
  $running | Stop-Process -Force
  Start-Sleep -Seconds 2
}

if ($CdpPort -le 0) {
  $CdpPort = Get-FreeTcpPort
} elseif (-not (Test-TcpPortAvailable $CdpPort)) {
  $requested = $CdpPort
  $CdpPort = Get-FreeTcpPort
  Write-Warning "CDP port $requested is already in use. Using free port $CdpPort instead."
}
Write-Host "Chromium DevTools port: $CdpPort"

$proc = Start-Process -FilePath $PgAdminExe -ArgumentList "--remote-debugging-port=$CdpPort" -PassThru
$cdp = "http://127.0.0.1:$CdpPort"
$ready = $false
for ($i=0; $i -lt 60; $i++) {
  if ($proc.HasExited) { break }
  try {
    Invoke-RestMethod "$cdp/json/version" -TimeoutSec 2 | Out-Null
    $ready = $true
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}
if (-not $ready) {
  if (-not $KeepPgAdmin -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
  $state = if ($proc.HasExited) { "pgAdmin exited with code $($proc.ExitCode)" } else { "pgAdmin is still running" }
  throw "pgAdmin did not expose Chromium DevTools at $cdp ($state)."
}

$exitCode = 0
try {
  & $VenvPython .\tests\e2e_pgadmin.py --cdp $cdp --screenshots .\artifacts\screenshots --report .\artifacts\e2e-report.json
  $exitCode = $LASTEXITCODE
} finally {
  if (-not $KeepPgAdmin -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
}

# Always publish screenshots/report, including failed runs.
if (-not $NoPush) {
  git add -A -- artifacts
  $changes = git status --porcelain -- artifacts
  if ($changes) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    git commit -m "test: refresh Hebrew pgAdmin E2E artifacts ($stamp)"
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    git push origin HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
  } else {
    Write-Host 'No artifact changes to commit.'
  }
}

if ($exitCode -ne 0) {
  throw "E2E test failed (exit $exitCode). Screenshots/report were preserved and pushed."
}
Write-Host 'ALL TESTS PASSED.' -ForegroundColor Green
