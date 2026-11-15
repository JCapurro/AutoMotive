<#
  Installs the prospecting bot (docs/PROSPECCION.md) as a scheduled task of the current user.
  Idempotent: run it again at any time. From the root of the main checkout:

    powershell -ExecutionPolicy Bypass -File ops\install-prospector.ps1

  Registers \AutoMotive\Prospector: every day at 7:30, python -m prospector from <checkout>\worker.
  StartWhenAvailable: if the PC was off at 7:30, the batch runs when it is turned on. The bot
  itself writes one batch per day (ultima-corrida.txt), so an extra run does nothing.
  The output goes to %LOCALAPPDATA%\EseAuto\prospeccion\prospector.log; each run leaves its
  report in ...\prospeccion\corridas. It starts nothing now. Remove it with
  ops\uninstall-prospector.ps1.
#>
param(
  [string]$Python = "",
  [string]$Claude = "",
  [string]$EnvFile = (Join-Path (Split-Path $PSScriptRoot -Parent) ".env"),
  [string]$At = "07:30"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$folder = "\AutoMotive\"

function Find-Tool([string]$value, [string]$command) {
  if ($value) { return $value }
  $found = Get-Command $command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $found) { throw "no encuentro $command en el PATH: pasalo con su parametro" }
  return $found.Source
}

$Python = Find-Tool $Python "python"
if ($Python -like "*\WindowsApps\*") { throw "python es el alias de la Microsoft Store: pasa -Python con la ruta del interprete" }
$Claude = Find-Tool $Claude "claude"
# A .cmd shim goes through cmd.exe, which mangles the empty --setting-sources and the JSON schema.
if ([IO.Path]::GetExtension($Claude) -ne ".exe") { throw "-Claude tiene que ser el claude.exe nativo, no $Claude" }
foreach ($path in @($Python, $Claude, $EnvFile)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "no existe: $path" }
}
$EnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
$worker = Join-Path $root "worker"
if (-not (Test-Path -LiteralPath (Join-Path $worker "prospector\run.py"))) { throw "no encuentro worker\prospector en $root" }

$state = Join-Path $env:LOCALAPPDATA "EseAuto\prospeccion"
New-Item -ItemType Directory -Force -Path $state | Out-Null
$logFile = Join-Path $state "prospector.log"

# PowerShell, hidden, so the output lands in a log file (pythonw would lose it).
$command = "`$env:CLAUDE_CLI_PATH = '$Claude'; & '$Python' -m prospector --env-file '$EnvFile' *>> '$logFile'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -Command `"$command`"" -WorkingDirectory $worker
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 3) -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskPath $folder -TaskName "Prospector" -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "tarea ${folder}Prospector registrada (python -m prospector, todos los dias a las $At)"
Write-Output "Antes de dejarla andar: & `"$Claude`" auth status"
Write-Output "Prueba sin escribir en la base: cd `"$worker`" ; & `"$Python`" -m prospector --env-file `"$EnvFile`" --dry-run --new 5"
