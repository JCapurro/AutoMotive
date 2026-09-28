<#
  Starts Docker Desktop if needed and then the local Supabase stack
  (F7, punto 8). Run at logon by install-tasks.ps1.
#>
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root "logs\supervisor.log"
New-Item -ItemType Directory -Force (Join-Path $root "logs") | Out-Null

function Test-Docker { docker info *> $null; return $LASTEXITCODE -eq 0 }

if (-not (Test-Docker)) {
  $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
  if (Test-Path $desktop) { Start-Process $desktop }
  $deadline = (Get-Date).AddMinutes(10)
  while (-not (Test-Docker) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 10 }
}
if (-not (Test-Docker)) {
  Add-Content $log "$(Get-Date -Format s) supabase: Docker no arranco en 10 min"
  exit 1
}
Set-Location $root
cmd /c "npx supabase start >> `"$(Join-Path $root 'logs\supabase.out.log')`" 2>&1"
Add-Content $log "$(Get-Date -Format s) supabase start ($LASTEXITCODE)"
exit $LASTEXITCODE
