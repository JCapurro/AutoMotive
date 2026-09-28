<#
  Deploys a new version on the pilot PC (F7, punto 8), from the repo root after
  `git pull`: migrations, Python and web dependencies, web build, and a restart
  of the Web and Worker tasks.

    powershell -ExecutionPolicy Bypass -File ops\update.ps1
#>
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$folder = "\AutoMotive\"
Set-Location $root

Write-Output "1/4 backup previo"
& (Join-Path $PSScriptRoot "backup.ps1")
Write-Output "2/4 migraciones"
cmd /c "npx supabase migration up"
if ($LASTEXITCODE -ne 0) { throw "migraciones: fallo" }
Write-Output "3/4 dependencias y build"
cmd /c "$Python -m pip install -q -r worker\requirements.txt"
Push-Location web
cmd /c "npm ci && npm run build"
$built = $LASTEXITCODE
Pop-Location
if ($built -ne 0) { throw "build de la web: fallo (la version anterior sigue corriendo)" }
Write-Output "4/4 reinicio de Web y Worker"
foreach ($name in "Web", "Worker") {
  Stop-ScheduledTask -TaskPath $folder -TaskName $name -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "main\.py|next start" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
foreach ($name in "Web", "Worker") { Start-ScheduledTask -TaskPath $folder -TaskName $name }
Write-Output "Listo."
