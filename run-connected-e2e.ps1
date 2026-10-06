param(
  [string]$Cdp = "",
  [switch]$NoPush
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  throw "Local .venv is missing. Run setup-and-test.ps1 first."
}

$BaseReport = Join-Path $Root "artifacts\e2e-report.json"
if (-not $Cdp) {
  if (-not (Test-Path $BaseReport)) {
    throw "Base E2E report not found. Run setup-and-test.ps1 -KeepPgAdmin first."
  }

  $base = Get-Content $BaseReport -Raw | ConvertFrom-Json
  $Cdp = [string]$base.diagnostics.cdp
}

if (-not $Cdp) {
  throw "No CDP endpoint found. Run setup-and-test.ps1 -KeepPgAdmin first."
}

try {
  Invoke-RestMethod "$($Cdp.TrimEnd('/'))/json/version" -TimeoutSec 3 | Out-Null
} catch {
  throw "The pgAdmin CDP endpoint is no longer available at $Cdp. Run setup-and-test.ps1 -KeepPgAdmin again."
}

$Artifacts = Join-Path $Root "artifacts"
$Screens = Join-Path $Artifacts "screenshots"
New-Item -ItemType Directory -Force -Path $Screens | Out-Null

$ConnectedReport = Join-Path $Artifacts "connected-e2e-report.json"
Remove-Item $ConnectedReport -Force -ErrorAction SilentlyContinue
@(
  "08-connected-database-tree.png",
  "09-query-tool.png",
  "10-backup-dialog.png",
  "11-restore-dialog.png"
) | ForEach-Object {
  Remove-Item (Join-Path $Screens $_) -Force -ErrorAction SilentlyContinue
}

Write-Host "Connected pgAdmin E2E"
Write-Host "CDP: $Cdp"
Write-Host "This run never executes SQL, Backup, or Restore actions."

& $VenvPython .\tests\e2e_connected_pgadmin.py --cdp $Cdp --screenshots .\artifacts\screenshots --report .\artifacts\connected-e2e-report.json
$exitCode = $LASTEXITCODE

if (-not $NoPush) {
  git add -A -- artifacts

  $changes = git status --porcelain -- artifacts
  if ($changes) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git commit -m "test: refresh connected Hebrew pgAdmin E2E artifacts ($stamp)"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

    git push origin HEAD
    if ($LASTEXITCODE -ne 0) { throw "git push failed." }
  } else {
    Write-Host "No connected artifact changes to commit."
  }
}

if ($exitCode -eq 2) {
  throw "No already-connected server was found. Leave pgAdmin open, connect PostgreSQL 18 manually, then run this script again."
}
if ($exitCode -ne 0) {
  throw "Connected E2E failed (exit $exitCode). The report/screenshots were preserved and pushed."
}

Write-Host "CONNECTED E2E PASSED." -ForegroundColor Green
