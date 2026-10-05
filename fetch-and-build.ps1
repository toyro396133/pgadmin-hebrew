param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pot = Join-Path $Root "messages-v9.18.pot"
$FullPo = Join-Path $Root "messages.full.po"
$Url = "https://raw.githubusercontent.com/pgadmin-org/pgadmin4/REL-9_18/web/pgadmin/messages.pot"

Write-Host "Checking local translation key-set integrity..."
& $Python (Join-Path $Root "verify_keyset.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Downloading official pgAdmin 4 v9.18 catalogue..."
Invoke-WebRequest -Uri $Url -OutFile $Pot

Write-Host "Verifying exact upstream catalogue coverage..."
& $Python (Join-Path $Root "verify_upstream.py") $Pot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Merging reviewed Hebrew translations..."
& $Python (Join-Path $Root "merge_into_template.py") $Pot $FullPo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running QA..."
& $Python (Join-Path $Root "qa_translation.py") $FullPo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Compiling messages.mo..."
& $Python -m babel.messages.frontend compile -i $FullPo -o (Join-Path $Root "messages.full.mo")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done."
