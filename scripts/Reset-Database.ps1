### BEGIN FILE: scripts\Reset-Database.ps1
<#
.SYNOPSIS
  Resets the app to a blank state by deleting the SQLite DB and clearing media files.
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

if (Test-Path $mediaDir) {
    Get-ChildItem -LiteralPath $mediaDir -File -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Cleared media: $mediaDir"
}

Write-Host "Reset complete."
### END FILE: scripts\Reset-Database.ps1
