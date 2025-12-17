### BEGIN FILE: scripts\Reset-Database.ps1
<#
.SYNOPSIS
  Resets the app to a blank state by deleting the SQLite DB and clearing media files.
  Run Setup.ps1 after this to recreate the DB via migrations.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot  = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($ScriptDir, '..'))

$dbPath   = Join-Path $RepoRoot 'data\family_tree.sqlite'
$mediaDir = Join-Path $RepoRoot 'data\media'

if (Test-Path $dbPath) {
    Remove-Item -LiteralPath $dbPath -Force
    Write-Host "Deleted DB: $dbPath"
}

# Also remove SQLite WAL and SHM files
$dbWal = "${dbPath}-wal"
$dbShm = "${dbPath}-shm"
if (Test-Path $dbWal) { Remove-Item -LiteralPath $dbWal -Force }
if (Test-Path $dbShm) { Remove-Item -LiteralPath $dbShm -Force }

if (Test-Path $mediaDir) {
    Get-ChildItem -LiteralPath $mediaDir -File -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Cleared media: $mediaDir"
}

Write-Host "Reset complete. Run .\scripts\Setup.ps1 to recreate the database."
### END FILE: scripts\Reset-Database.ps1
