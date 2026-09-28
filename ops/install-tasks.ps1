<#
  Registers the pilot as Windows scheduled tasks of the current user
  (F7, punto 8). Run once from an elevated PowerShell, from the repo root:

    powershell -ExecutionPolicy Bypass -File ops\install-tasks.ps1 -BackupDest "$env:OneDrive\AutoMotive\backups"

  Tasks (all under \AutoMotive\):
    Supabase   at logon: Docker Desktop + npx supabase start
    Web        at logon: next start on 127.0.0.1:3000 (supervised, restarts)
    Worker     at logon: python main.py (supervised, restarts)
    Watchdog   every 5 min: python -m tools.watchdog (Telegram to the admin)
    Backup     daily 03:30: ops\backup.ps1
  Remove them with ops\uninstall-tasks.ps1.
#>
param(
  [string]$Python = "python",
  [string]$BackupDest = (Join-Path (Split-Path $PSScriptRoot -Parent) "backups"),
  [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$folder = "\AutoMotive\"

if (-not $SkipBuild) {
  Write-Output "Compilando la web (npm ci + npm run build)..."
  Push-Location (Join-Path $root "web")
  cmd /c "npm ci && npm run build"
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "el build de la web fallo" }
  Pop-Location
}

function PS([string]$script, [string]$arguments = "") {
  New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot $script)`" $arguments"
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$logon = New-ScheduledTaskTrigger -AtLogOn -User $user
$longRunning = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$short = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

$tasks = @(
  @{ Name = "Supabase"; Action = (PS "start-supabase.ps1"); Trigger = $logon; Settings = $short },
  @{ Name = "Web"; Trigger = $logon; Settings = $longRunning;
     Action = (PS "run-forever.ps1" "-Name web -WorkDir web -Command `"npm run start -- --hostname 127.0.0.1 --port 3000`"") },
  @{ Name = "Worker"; Trigger = $logon; Settings = $longRunning;
     Action = (PS "run-forever.ps1" "-Name worker -WorkDir worker -Command `"$Python main.py`"") },
  @{ Name = "Watchdog"; Settings = $short;
     Trigger = (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(10) -RepetitionInterval (New-TimeSpan -Minutes 5));
     Action = (New-ScheduledTaskAction -Execute "cmd.exe" -WorkingDirectory (Join-Path $root "worker") `
               -Argument "/c $Python -m tools.watchdog >> `"$(Join-Path $root 'logs\watchdog.log')`" 2>&1") },
  @{ Name = "Backup"; Settings = $short; Trigger = (New-ScheduledTaskTrigger -Daily -At "03:30");
     Action = (PS "backup.ps1" "-Dest `"$BackupDest`"") }
)
foreach ($t in $tasks) {
  Register-ScheduledTask -TaskPath $folder -TaskName $t.Name -Action $t.Action -Trigger $t.Trigger `
    -Settings $t.Settings -Principal $principal -Force | Out-Null
  Write-Output "tarea $folder$($t.Name) registrada"
}
Write-Output "Listo. Arrancan en el proximo inicio de sesion, o ahora con: Get-ScheduledTask -TaskPath $folder | Start-ScheduledTask"
