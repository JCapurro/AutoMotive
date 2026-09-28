<#
  Supervisor (F7, punto 8): runs a command and restarts it when it exits,
  with backoff (10 s doubling up to 5 min; back to 10 s after 10 min up).
  Output goes to logs\<Name>.out.log (rotated at 20 MB); starts and exits to
  logs\supervisor.log. Used by the scheduled tasks of install-tasks.ps1.

  .\ops\run-forever.ps1 -Name worker -WorkDir worker -Command "python main.py"
#>
param(
  [Parameter(Mandatory)][string]$Name,
  [Parameter(Mandatory)][string]$WorkDir,
  [Parameter(Mandatory)][string]$Command
)
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$out = Join-Path $logs "$Name.out.log"
$supervisor = Join-Path $logs "supervisor.log"
$dir = if ([IO.Path]::IsPathRooted($WorkDir)) { $WorkDir } else { Join-Path $root $WorkDir }
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
$delay = 10

while ($true) {
  if ((Test-Path $out) -and (Get-Item $out).Length -gt 20MB) { Move-Item -Force $out "$out.1" }
  $started = Get-Date
  Add-Content $supervisor "$(Get-Date -Format s) $Name start: $Command"
  cmd /c "cd /d `"$dir`" && $Command >> `"$out`" 2>&1"
  $code = $LASTEXITCODE
  $delay = if (((Get-Date) - $started).TotalMinutes -ge 10) { 10 } else { [Math]::Min($delay * 2, 300) }
  Add-Content $supervisor "$(Get-Date -Format s) $Name exited ($code); restarting in $delay s"
  Start-Sleep -Seconds $delay
}
