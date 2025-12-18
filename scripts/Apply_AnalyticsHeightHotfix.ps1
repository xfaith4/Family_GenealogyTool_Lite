param(
  [Parameter(Mandatory)] [string]$RepoRoot,
  [Parameter(Mandatory)] [string]$HotfixZipPath
)

if (-not (Test-Path -LiteralPath $RepoRoot))     { throw "RepoRoot not found: $($RepoRoot)" }
if (-not (Test-Path -LiteralPath $HotfixZipPath)){ throw "HotfixZipPath not found: $($HotfixZipPath)" }

$stage = Join-Path $env:TEMP ("AnalyticsHotfix_{0}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Expand-Archive -LiteralPath $HotfixZipPath -DestinationPath $stage -Force

$files = @(
  'app\templates\analytics.html',
  'app\static\styles.css',
  'app\static\analytics.js'
)

foreach($rel in $files){
  $src = Join-Path $stage   $rel
  $dst = Join-Path $RepoRoot $rel
  if (-not (Test-Path -LiteralPath $src)) { throw "Missing hotfix file: $($src)" }

  $dstDir = Split-Path -Parent $dst
  if (-not (Test-Path -LiteralPath $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }

  Copy-Item -LiteralPath $src -Destination $dst -Force
  Write-Host "Patched: $rel"
}

Write-Host "`nHotfix applied. Refresh /analytics (hard refresh recommended)." -ForegroundColor Green
