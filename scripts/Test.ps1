### BEGIN FILE: scripts\Test.ps1
<#
.SYNOPSIS
  Runs unit tests (unittest).
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot  = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($ScriptDir, '..'))

$python = $null
foreach ($candidate in @('py', 'python', 'python3')) {
    try { & $candidate -V *> $null; $python = $candidate; break } catch { }
}
if (-not $python) { throw "Python not found. Install Python 3.11+ and ensure it is on PATH." }

Push-Location $RepoRoot
try {
    & $python -m unittest discover -s tests -v
} finally {
    Pop-Location
}
### END FILE: scripts\Test.ps1
