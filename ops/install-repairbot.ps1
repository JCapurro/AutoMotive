<#
  Installs the collector repair bot (docs/COLLECTOR_REPAIR.md) as a scheduled task of the
  current user. Idempotent: run it again at any time. From the root of the main checkout:

    powershell -ExecutionPolicy Bypass -File ops\install-repairbot.ps1

  Creates <BotHome>\state and \runs and, when missing, two separate clones of the repo:
  <BotHome>\repo, where Claude works (reset to origin/main around every attempt), and
  <BotHome>\launcher, the code the task runs (the bot fast-forwards it at the end of every
  tick; Claude never touches it). Writes <BotHome>\config.json only when it does not exist yet
  (an existing one decides the paths), and registers \AutoMotive\RepairBot (every 5 minutes:
  python -m repairbot from <launcher>\worker).
  It starts nothing and never touches the VPS. Remove the task with ops\uninstall-repairbot.ps1.
#>
param(
  [string]$BotHome = "C:\automotive-bot",
  [string]$Python = "",
  [string]$EnvFile = (Join-Path (Split-Path $PSScriptRoot -Parent) ".env"),
  [string]$Claude = "",
  [string]$GitBash = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$folder = "\AutoMotive\"
$origin = "https://github.com/JCapurro/AutoMotive.git"

function Find-Tool([string]$value, [string]$command) {
  if ($value) { return $value }
  $found = Get-Command $command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $found) { throw "no encuentro $command en el PATH: pasalo con su parametro" }
  return $found.Source
}

function Same-Remote([string]$a, [string]$b) {
  $clean = { param($url) ($url.Trim().TrimEnd('/') -replace '\.git$', '').ToLowerInvariant() }
  return (& $clean $a) -eq (& $clean $b)
}

function Is-Inside([string]$path, [string]$folder) {
  return $path.StartsWith($folder.TrimEnd('\') + "\", [StringComparison]::OrdinalIgnoreCase)
}

# A clone of its own (.git is a folder, not a worktree's file) whose origin is the repository.
function Ensure-Clone([string]$path) {
  if (Test-Path -LiteralPath (Join-Path $path ".git") -PathType Container) {
    $current = git -C $path remote get-url origin
    if ($LASTEXITCODE -ne 0 -or -not (Same-Remote $current $origin)) { throw "$path no es un clon de $origin" }
    Write-Output "clon existente: $path"
  } else {
    if (Test-Path -LiteralPath $path) { throw "$path existe y no es un clon de git: movelo o borralo a mano" }
    Write-Output "clonando $origin en $path..."
    git clone --quiet $origin $path
    if ($LASTEXITCODE -ne 0) { throw "git clone fallo" }
  }
}

$Python = Find-Tool $Python "python"
if ($Python -like "*\WindowsApps\*") { throw "python es el alias de la Microsoft Store: pasa -Python con la ruta del interprete" }
$Claude = Find-Tool $Claude "claude"
# A .cmd shim goes through cmd.exe, which mangles the empty --setting-sources and the JSON schema.
if ([IO.Path]::GetExtension($Claude) -ne ".exe") { throw "-Claude tiene que ser el claude.exe nativo, no $Claude" }
if (-not $GitBash) {
  $git = Find-Tool "" "git"                                   # ...\Git\cmd\git.exe
  $GitBash = Join-Path (Split-Path (Split-Path $git -Parent) -Parent) "bin\bash.exe"
}
foreach ($path in @($Python, $Claude, $GitBash, $EnvFile)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "no existe: $path" }
}
$BotHome = [IO.Path]::GetFullPath($BotHome)
$EnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
$config = Join-Path $BotHome "config.json"
$repo = Join-Path $BotHome "repo"
$launcher = Join-Path $BotHome "launcher"
if (Test-Path -LiteralPath $config) {
  # config.json is never rewritten: the clones and the task follow its paths. One written before
  # the launcher had its own clone has no "launcher": the bot then uses <home>\launcher.
  $existing = [IO.File]::ReadAllText($config) | ConvertFrom-Json
  if ($existing.repo) { $repo = [IO.Path]::GetFullPath($existing.repo) }
  if ($existing.launcher) { $launcher = [IO.Path]::GetFullPath($existing.launcher) }
  elseif ($existing.home) { $launcher = Join-Path ([IO.Path]::GetFullPath($existing.home)) "launcher" }
}
if ($launcher -ieq $repo -or (Is-Inside $launcher $repo) -or (Is-Inside $repo $launcher)) {
  throw "el clon del lanzador ($launcher) y el de trabajo de Claude ($repo) tienen que ser carpetas separadas"
}
foreach ($clone in @($repo, $launcher)) {
  if (Is-Inside $EnvFile $clone) { throw "el .env no puede estar dentro de $clone (el bot limpia su clon de trabajo y no acepta un lanzador que lo contenga)" }
}

foreach ($dir in @($BotHome, (Join-Path $BotHome "state"), (Join-Path $BotHome "runs"))) {
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

Ensure-Clone $repo
Ensure-Clone $launcher
# The bot commits (in the work clone only) as the owner of the main checkout.
foreach ($key in @("user.name", "user.email")) {
  $value = git -C $root config $key
  if ($LASTEXITCODE -ne 0 -or -not $value) { throw "el checkout principal no tiene $key configurado" }
  git -C $repo config $key "$value"
  if ($LASTEXITCODE -ne 0) { throw "no se pudo configurar $key en el clon" }
}

if (Test-Path -LiteralPath $config) {
  Write-Output "config.json ya existe, no se toca: $config"
} else {
  $data = [ordered]@{
    home = $BotHome; repo = $repo; launcher = $launcher; env_file = $EnvFile
    python = $Python; claude = $Claude; git_bash = $GitBash
  }
  # Python's json.loads rejects a BOM, and Set-Content in Windows PowerShell writes one.
  [IO.File]::WriteAllText($config, ($data | ConvertTo-Json) + "`n", (New-Object Text.UTF8Encoding $false))
  Write-Output "config.json escrito: $config"
}

# pythonw has no console: the task does not flash a window every 5 minutes. It runs the launcher's
# clone, never the one Claude edits: its imports never load the session's unreviewed code.
$pythonw = Join-Path (Split-Path $Python -Parent) "pythonw.exe"
$runner = if (Test-Path -LiteralPath $pythonw) { $pythonw } else { $Python }
$action = New-ScheduledTaskAction -Execute $runner -Argument "-m repairbot --config `"$config`"" `
  -WorkingDirectory (Join-Path $launcher "worker")
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 90) -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskPath $folder -TaskName "RepairBot" -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "tarea ${folder}RepairBot registrada ($runner -m repairbot, cada 5 minutos)"
Write-Output "Antes de dejarla andar: & `"$Claude`" auth status ; ssh -o BatchMode=yes automotive-vps true"
Write-Output "Prueba sin efectos: cd `"$launcher\worker`" ; & `"$Python`" -m repairbot --config `"$config`" --dry-run"
