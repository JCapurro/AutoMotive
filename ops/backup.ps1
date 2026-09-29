<#
  Daily database backup (F7, punto 8): pg_dump (custom format) of the hosted
  Supabase database (public, auth and the migration history) to -Dest,
  keeping the -Keep newest. Point -Dest at a folder that leaves the PC
  (OneDrive, Google Drive...).

  pg_dump runs in the postgres:17 Docker image (same major as the project),
  against DATABASE_URL from the root .env; Docker Desktop is started if needed.

  .\ops\backup.ps1 -Dest "$env:OneDrive\AutoMotive\backups"
  Restore: docs\PILOT_SETUP.md, "Restaurar un backup".
#>
param(
  [string]$Dest = (Join-Path (Split-Path $PSScriptRoot -Parent) "backups"),
  [int]$Keep = 14,
  [string]$Image = "postgres:17"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

# Native stderr (docker's warnings) must not stop the script: only exit codes count.
function Test-Docker { $ErrorActionPreference = "Continue"; docker info *> $null; return $LASTEXITCODE -eq 0 }

# The URL carries the password: it goes to the container as an environment
# variable, never on a command line or in the output.
$line = Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
if (-not $line) { throw "falta DATABASE_URL en .env" }
$env:PGURL = $line.Substring("DATABASE_URL=".Length).Trim()

if (-not (Test-Docker)) {
  $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
  if (Test-Path $desktop) { Start-Process $desktop }
  $deadline = (Get-Date).AddMinutes(10)
  while (-not (Test-Docker) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 10 }
  if (-not (Test-Docker)) { throw "Docker no arranco en 10 min" }
}

New-Item -ItemType Directory -Force $Dest | Out-Null
$Dest = (Resolve-Path $Dest).Path
$name = "automotive-{0}.dump" -f (Get-Date -Format "yyyyMMdd-HHmm")
$ErrorActionPreference = "Continue"
docker run --rm -e PGURL -v "${Dest}:/out" $Image `
  sh -c "set -f; pg_dump `$PGURL -Fc -n public -n auth -n supabase_migrations -f /out/$name"
if ($LASTEXITCODE -ne 0) { throw "pg_dump fallo ($LASTEXITCODE)" }
$ErrorActionPreference = "Stop"
$file = Join-Path $Dest $name
Get-ChildItem $Dest -Filter "automotive-*.dump" | Sort-Object LastWriteTime -Descending |
  Select-Object -Skip $Keep | Remove-Item
Write-Output ("backup: {0} ({1:N1} MB)" -f $file, ((Get-Item $file).Length / 1MB))
