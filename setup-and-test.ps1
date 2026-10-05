param(
  [string]$WebPath = "",
  [int]$CdpPort = 9222,
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
    $candidates += Get-ChildItem "$env:ProgramFiles\PostgreSQL" -Directory -ErrorAction SilentlyContinue | ForEach-Object { Join-Path $_.FullName 'pgAdmin 4\web' }
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
  foreach ($p in $candidates) { if ($p -and (Test-Path $p)) { return (Resolve-Path $p).Path } }
  throw 'pgAdmin4.exe not found next to the detected web directory.'
}

$WebPath = Find-WebPath $WebPath
$PgAdminExe = Find-PgAdminExe $WebPath
Write-Host "pgAdmin web: $WebPath"
Write-Host "pgAdmin exe: $PgAdminExe"

# Clean screenshots/report from the previous run. Git will record removals and new files together.
$Artifacts = Join-Path $Root 'artifacts'
$Screens = Join-Path $Artifacts 'screenshots'
New-Item -ItemType Directory -Force -Path $Screens | Out-Null
Get-ChildItem $Screens -File -ErrorAction SilentlyContinue | Remove-Item -Force
Remove-Item (Join-Path $Artifacts 'e2e-report.json') -Force -ErrorAction SilentlyContinue

# Python dependencies used by QA/E2E. Browser download is not needed; we attach to pgAdmin's Electron via CDP.
python -m pip install --disable-pip-version-check -q Babel==2.18.0 Jinja2 playwright

# Static/local QA first.
python .\qa_translation.py
python .\verify_keyset.py
python .\verify_rtl.py
if (Test-Path .\messages-v9.18.pot) { python .\verify_upstream.py .\messages-v9.18.pot } else { Write-Host 'Upstream POT file not present; offline REL-9_18 key-set fingerprint already verified.' }

# Install Hebrew + RTL into the detected pgAdmin 9.18 tree.
powershell -ExecutionPolicy Bypass -File .\install-hebrew.ps1 -WebPath $WebPath

# A clean Electron launch is required for DevTools/CDP attachment.
$running = Get-Process pgAdmin4 -ErrorAction SilentlyContinue
if ($running) {
  Write-Host 'Closing running pgAdmin4 processes for the UI test...'
  $running | Stop-Process -Force
  Start-Sleep -Seconds 2
}

$proc = Start-Process -FilePath $PgAdminExe -ArgumentList "--remote-debugging-port=$CdpPort" -PassThru
$cdp = "http://127.0.0.1:$CdpPort"
$ready = $false
for ($i=0; $i -lt 60; $i++) {
  try { Invoke-RestMethod "$cdp/json/version" -TimeoutSec 2 | Out-Null; $ready=$true; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) {
  if (-not $KeepPgAdmin) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
  throw "pgAdmin did not expose Chromium DevTools at $cdp."
}

$exitCode = 0
try {
  python .\tests\e2e_pgadmin.py --cdp $cdp --screenshots .\artifacts\screenshots --report .\artifacts\e2e-report.json
  $exitCode = $LASTEXITCODE
} finally {
  if (-not $KeepPgAdmin) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}

# Always publish screenshots/report, including failed runs, so the failure can be inspected remotely.
if (-not $NoPush) {
  git add -A -- artifacts
  $changes = git status --porcelain -- artifacts
  if ($changes) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    git commit -m "test: refresh Hebrew pgAdmin E2E artifacts ($stamp)"
    git push origin HEAD
  } else {
    Write-Host 'No artifact changes to commit.'
  }
}

if ($exitCode -ne 0) { throw "E2E test failed (exit $exitCode). Screenshots/report were preserved and pushed." }
Write-Host 'ALL TESTS PASSED.' -ForegroundColor Green
