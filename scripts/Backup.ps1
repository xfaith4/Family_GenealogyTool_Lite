### BEGIN FILE: scripts\Backup.ps1
<#
.SYNOPSIS
  Creates a backup of the database and media files.

.DESCRIPTION
  - Copies family_tree.sqlite with timestamp
  - Optionally copies media folder
  - Stores in ./backups/{timestamp}/
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot  = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($ScriptDir, '..'))

Write-Host "RepoRoot: $RepoRoot"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupName = "backup_$Timestamp"
$BackupDir = Join-Path $RepoRoot "backups\$BackupName"

# Create backup directory
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
Write-Host "Creating backup: $BackupName"

# Backup database
$DbPath = Join-Path $RepoRoot "data\family_tree.sqlite"
if (Test-Path $DbPath) {
    Copy-Item -Path $DbPath -Destination (Join-Path $BackupDir "family_tree.sqlite")
    $DbSize = (Get-Item $DbPath).Length
    Write-Host "  Database backed up ($DbSize bytes)"
} else {
    Write-Host "  Warning: Database not found at $DbPath"
}

# Backup media folder
$MediaDir = Join-Path $RepoRoot "data\media"
if (Test-Path $MediaDir) {
    $MediaFiles = Get-ChildItem -Path $MediaDir -File
    if ($MediaFiles.Count -gt 0) {
        Copy-Item -Path $MediaDir -Destination (Join-Path $BackupDir "media") -Recurse
        Write-Host "  Media folder backed up ($($MediaFiles.Count) files)"
    } else {
        Write-Host "  Media folder is empty, skipping"
    }
} else {
    Write-Host "  Media folder not found, skipping"
}

Write-Host ""
Write-Host "Backup complete: $BackupDir"
Write-Host ""
Write-Host "To restore this backup, run:"
Write-Host "  .\scripts\Restore.ps1 -BackupName $BackupName"
### END FILE: scripts\Backup.ps1
