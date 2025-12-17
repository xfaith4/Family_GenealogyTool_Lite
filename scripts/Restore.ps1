### BEGIN FILE: scripts\Restore.ps1
<#
.SYNOPSIS
  Restores database and media from a backup.

.DESCRIPTION
  - Restores family_tree.sqlite from backup
  - Restores media folder if present
  - Requires backup name (timestamp)

.PARAMETER BackupName
  The name of the backup folder (e.g., backup_20231217_120000)
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupName
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot  = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($ScriptDir, '..'))

Write-Host "RepoRoot: $RepoRoot"

$BackupDir = Join-Path $RepoRoot "backups\$BackupName"

if (-not (Test-Path $BackupDir)) {
    Write-Error "Backup not found: $BackupDir"
    exit 1
}

Write-Host "Restoring from backup: $BackupName"

# Restore database
$BackupDb = Join-Path $BackupDir "family_tree.sqlite"
if (Test-Path $BackupDb) {
    $DbPath = Join-Path $RepoRoot "data\family_tree.sqlite"
    
    # Create data directory if it doesn't exist
    $DataDir = Join-Path $RepoRoot "data"
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    
    Copy-Item -Path $BackupDb -Destination $DbPath -Force
    Write-Host "  Database restored"
} else {
    Write-Error "No database file found in backup: $BackupDb"
    exit 1
}

# Restore media folder
$BackupMedia = Join-Path $BackupDir "media"
if (Test-Path $BackupMedia) {
    $MediaDir = Join-Path $RepoRoot "data\media"
    
    # Remove existing media
    if (Test-Path $MediaDir) {
        Remove-Item -Path $MediaDir -Recurse -Force
    }
    
    Copy-Item -Path $BackupMedia -Destination $MediaDir -Recurse
    $MediaCount = (Get-ChildItem -Path $MediaDir -File).Count
    Write-Host "  Media folder restored ($MediaCount files)"
} else {
    Write-Host "  No media folder in backup, skipping"
}

Write-Host ""
Write-Host "Restore complete!"
### END FILE: scripts\Restore.ps1
