param(
    [string]$WebPath = "",
    [string]$Python = "python",
    [switch]$NoRtl,
    [switch]$Restore,
    [switch]$Force,
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Installer = Join-Path $Root "install_hebrew.py"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Test-NeedsElevation([string]$Path) {
    if ($env:OS -ne "Windows_NT") { return $false }
    if (-not $Path) { return $false }

    try {
        $resolved = (Resolve-Path $Path).Path
    } catch {
        $resolved = $Path
    }

    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $protectedRoots = @(
        $env:ProgramFiles,
        $programFilesX86,
        $env:windir
    ) | Where-Object { $_ }

    foreach ($rootPath in $protectedRoots) {
        try {
            $rootResolved = (Resolve-Path $rootPath).Path.TrimEnd('\')
        } catch {
            $rootResolved = $rootPath.TrimEnd('\')
        }
        if ($resolved.StartsWith(
            $rootResolved + '\',
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            return $true
        }
    }
    return $false
}

# Elevate only the write step into protected Windows directories. This keeps
# the parent test runner, git operations and user environment non-elevated.
if (
    -not $Elevated -and
    (Test-NeedsElevation $WebPath) -and
    -not (Test-IsAdministrator)
) {
    Write-Host "Administrator permission is required to update pgAdmin under Program Files."
    Write-Host "Approve the Windows UAC prompt to continue."

    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $MyInvocation.MyCommand.Path),
        "-WebPath", ('"{0}"' -f $WebPath),
        "-Python", ('"{0}"' -f $Python),
        "-Elevated"
    )
    if ($NoRtl) { $argList += "-NoRtl" }
    if ($Restore) { $argList += "-Restore" }
    if ($Force) { $argList += "-Force" }

    try {
        $proc = Start-Process `
            -FilePath "powershell.exe" `
            -ArgumentList $argList `
            -Verb RunAs `
            -Wait `
            -PassThru
    } catch {
        Write-Error "Elevation was cancelled or failed: $($_.Exception.Message)"
        exit 1
    }

    exit $proc.ExitCode
}

$Args = @($Installer)
if ($WebPath) { $Args += @("--web-path", $WebPath) }
if ($NoRtl) { $Args += "--no-rtl" }
if ($Restore) { $Args += "--restore" }
if ($Force) { $Args += "--force" }

& $Python @Args
exit $LASTEXITCODE
