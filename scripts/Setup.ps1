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
$DataDir   = [System.IO.Path]::Combine($RepoRoot, 'data')
$DbPath    = [System.IO.Path]::Combine($DataDir, 'family_tree.sqlite')

Write-Host "RepoRoot: $RepoRoot"
Write-Host "Database path: $DbPath"

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

# Ensure database is reset before running migrations to avoid missing columns
Write-Host "Removing existing database to avoid schema conflicts..."
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$dbWal = "${DbPath}-wal"
$dbShm = "${DbPath}-shm"
try {
    if (Test-Path $DbPath) { Remove-Item $DbPath -Force -ErrorAction Stop; Write-Host "Deleted $DbPath" }
    else { Write-Host "No existing DB found at $DbPath" }
    if (Test-Path $dbWal) { Remove-Item $dbWal -Force -ErrorAction Stop; Write-Host "Deleted $dbWal" }
    if (Test-Path $dbShm) { Remove-Item $dbShm -Force -ErrorAction Stop; Write-Host "Deleted $dbShm" }
} catch {
    throw "Failed to remove existing database at $DbPath. Close any open handles and try again. $_"
}

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
