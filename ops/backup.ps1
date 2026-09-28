<#
  Daily database backup (F7, punto 8): pg_dump (custom format) of the whole
  local Supabase database (public, auth...) to -Dest, keeping the -Keep newest.
  Point -Dest at a folder that leaves the PC (OneDrive, Google Drive...).

  .\ops\backup.ps1 -Dest "$env:OneDrive\AutoMotive\backups"
  Restore: docs\PILOT_SETUP.md, "Restaurar un backup".
#>
param(
  [string]$Dest = (Join-Path (Split-Path $PSScriptRoot -Parent) "backups"),
  [int]$Keep = 14,
  [string]$Container = "supabase_db_automotive"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Dest | Out-Null
$file = Join-Path $Dest ("automotive-{0}.dump" -f (Get-Date -Format "yyyyMMdd-HHmm"))
docker exec $Container pg_dump -U supabase_admin -d postgres -Fc -f /tmp/automotive.dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump fallo ($LASTEXITCODE)" }
docker cp "${Container}:/tmp/automotive.dump" $file
if ($LASTEXITCODE -ne 0) { throw "docker cp fallo ($LASTEXITCODE)" }
docker exec $Container rm -f /tmp/automotive.dump | Out-Null
Get-ChildItem $Dest -Filter "automotive-*.dump" | Sort-Object LastWriteTime -Descending |
  Select-Object -Skip $Keep | Remove-Item
Write-Output ("backup: {0} ({1:N1} MB)" -f $file, ((Get-Item $file).Length / 1MB))
