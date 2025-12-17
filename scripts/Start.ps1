### BEGIN FILE: scripts\Start.ps1
<#
.SYNOPSIS
  Starts the web app locally.
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
    Write-Host "Listening on http://127.0.0.1:3001"
    & $python .\run.py
} finally {
    Pop-Location
}
### END FILE: scripts\Start.ps1
