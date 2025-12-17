### BEGIN FILE: scripts\Setup.ps1
<#
.SYNOPSIS
  Installs minimal dependencies and initializes DB with Alembic migrations.

.DESCRIPTION
  - No venv required (optional later)
  - Dependencies: Flask, SQLAlchemy, Alembic
  - Creates ./data/family_tree.sqlite via Alembic migrations
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

# Install dependencies
Write-Host "Installing requirements..."
& $python -m pip install --upgrade pip | Out-Host
& $python -m pip install -r (Join-Path $RepoRoot 'requirements.txt') | Out-Host

# Run Alembic migrations
Write-Host "Running database migrations..."
Push-Location $RepoRoot
try {
    & $python -m alembic upgrade head | Out-Host
} finally {
    Pop-Location
}

Write-Host "Setup complete."
### END FILE: scripts\Setup.ps1
