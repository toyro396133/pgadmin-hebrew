param(
    [string]$WebPath = "",
    [string]$Python = "python",
    [switch]$NoRtl,
    [switch]$Restore,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $Root "install_hebrew.py"

$Args = @($Installer)
if ($WebPath) { $Args += @("--web-path", $WebPath) }
if ($NoRtl) { $Args += "--no-rtl" }
if ($Restore) { $Args += "--restore" }
if ($Force) { $Args += "--force" }

& $Python @Args
exit $LASTEXITCODE
