### BEGIN FILE: scripts\Setup.ps1
<#
.SYNOPSIS
  Installs minimal dependencies and initializes an empty SQLite DB.

.DESCRIPTION
  - No venv required (optional later)
  - Only dependency is Flask
  - Creates ./data/family_tree.sqlite (schema is auto-created) if missing
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot  = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($ScriptDir, '..'))

Write-Host "RepoRoot: $RepoRoot"

# Locate Python
$python = $null
foreach ($candidate in @('py', 'python', 'python3')) {
    try {
        & $candidate -V *> $null
        $python = $candidate
        break
    } catch { }
}
if (-not $python) { throw "Python not found. Install Python 3.11+ and ensure it is on PATH." }

# Install dependency
Write-Host "Installing requirements..."
& $python -m pip install --upgrade pip | Out-Host
& $python -m pip install -r (Join-Path $RepoRoot 'requirements.txt') | Out-Host

# Initialize DB (importing app triggers schema init)
Write-Host "Initializing DB..."
Push-Location $RepoRoot
try {
    & $python -c "from app import create_app; a=create_app(); print(a.config['DATABASE'])" | Out-Host
} finally {
    Pop-Location
}

Write-Host "Setup complete."
### END FILE: scripts\Setup.ps1
