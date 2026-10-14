<#
  Deploys a new version on the pilot PC (F7, punto 8), from the repo root after
  `git pull`: migrations (to the hosted Supabase database), Python and web
  dependencies, web build, and a restart of the Web and Worker tasks. A task
  that is Disabled is never started (Worker: the worker runs on the VPS).

  The running `next start` keeps native modules of web\node_modules open, so Web
  is stopped for the build. Meanwhile the running version's web\node_modules and
  web\.next wait in .update\previous: if the build fails they go back to web\ and
  Web starts again with them.

    powershell -ExecutionPolicy Bypass -File ops\update.ps1
#>
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$folder = "\AutoMotive\"
$web = Join-Path $root "web"
$builds = "node_modules", ".next"
$stash = Join-Path $root ".update"
$previous = Join-Path $stash "previous"
$trash = Join-Path $stash "trash"
Set-Location $root

# A task's own processes: its supervisor (ops\run-forever.ps1 -Name <name>) and
# everything below it (cmd, npm, next or python), which outlives Stop-ScheduledTask.
function Stop-TaskProcesses([string]$name) {
  $pattern = [regex]::Escape((Join-Path $PSScriptRoot "run-forever.ps1")) + ".* -Name $name\b"
  $tree = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $pattern })
  # The supervisor goes first, so it can't start another child while the rest is collected.
  Stop-ScheduledTask -TaskPath $folder -TaskName $name -ErrorAction SilentlyContinue
  foreach ($p in $tree) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  $all = @(Get-CimInstance Win32_Process)
  for ($i = 0; $i -lt $tree.Count; $i++) {
    $parent = $tree[$i]
    # A child can't be older than its parent; an older one has a reused parent id.
    $tree += @($all | Where-Object { $_.ParentProcessId -eq $parent.ProcessId -and
      $_.CreationDate -ge $parent.CreationDate -and $tree.ProcessId -notcontains $_.ProcessId })
  }
  foreach ($p in $tree) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  if ($tree) { Wait-Process -Id $tree.ProcessId -Timeout 30 -ErrorAction SilentlyContinue }
}

function Restart-Task([string]$name) {
  $task = Get-ScheduledTask -TaskPath $folder -TaskName $name -ErrorAction SilentlyContinue
  if (-not $task -or $task.State -eq "Disabled") {
    Write-Output "    $folder$name no se arranca: $(if ($task) { 'esta deshabilitada' } else { 'no existe' })"
    return
  }
  Stop-TaskProcesses $name
  Start-ScheduledTask -TaskPath $folder -TaskName $name
  Write-Output "    $folder$name arrancada"
}

# A rename on the same volume: it moves everything or nothing (Move-Item, when the
# rename fails, moves what it can and leaves the rest). Retries for a moment in
# case a file of a just-stopped process is still held (an antivirus).
function Move-Tree([string]$from, [string]$to) {
  if (-not (Test-Path -LiteralPath $from)) { return }
  if (Test-Path -LiteralPath $to) { throw "ya existe $to" }
  New-Item -ItemType Directory -Force (Split-Path $to -Parent) | Out-Null
  for ($try = 1; ; $try++) {
    try { [IO.Directory]::Move($from, $to); return }
    catch { if ($try -ge 5) { throw } }
    Start-Sleep -Seconds 2
  }
}

function Move-ToTrash([string]$path) {
  Move-Tree $path (Join-Path $trash ([guid]::NewGuid().ToString("N")))
}

# previous\ goes to the trash first: half deleted, it would look like a cut-off run.
function Remove-Stash {
  try {
    Move-ToTrash $previous
    if (Test-Path -LiteralPath $stash) { Remove-Item -LiteralPath $stash -Recurse -Force }
  } catch { Write-Warning "no se pudo borrar $stash ($_); borralo a mano" }
}

# Left by a run that died between moving the running version aside and putting it back.
if (Get-ChildItem -LiteralPath $previous -Force -ErrorAction SilentlyContinue) {
  throw "quedo $previous de una actualizacion cortada, con node_modules y .next de la version anterior. Si la web local anda, borralo; si no, devolvelos a web\ y volve a correr."
}
Remove-Stash

Write-Output "1/4 backup previo"
& (Join-Path $PSScriptRoot "backup.ps1")
Write-Output "2/4 migraciones (base de Supabase en la nube)"
$line = Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
if (-not $line) { throw "falta DATABASE_URL en .env" }
# Only the pending migrations; seed.sql is idempotent and never overwrites tuned values.
cmd /c "npx supabase db push --yes --include-seed --db-url `"$($line.Substring('DATABASE_URL='.Length).Trim())`""
if ($LASTEXITCODE -ne 0) { throw "migraciones: fallo" }
Write-Output "3/4 dependencias y build (la web local queda parada hasta que termine)"
cmd /c "$Python -m pip install -q -r worker\requirements.txt"
$ok = $false
try {
  Stop-TaskProcesses "Web"
  try { foreach ($d in $builds) { Move-Tree (Join-Path $web $d) (Join-Path $previous $d) } }
  catch {
    $err = $_
    $users = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match [regex]::Escape("$web\") } |
      ForEach-Object { "`n    $($_.ProcessId) $($_.CommandLine)" }
    throw "web\node_modules o web\.next siguen en uso (un next dev o el e2e corriendo desde web\?): cerralo y volve a correr.$users`n$err"
  }
  cmd /c "cd /d `"$web`" && npm ci && npm run build"
  $ok = $LASTEXITCODE -eq 0
} finally {
  if (-not $ok) {
    # Only what was moved aside goes back; the failed build's leftovers go to the trash.
    try {
      foreach ($d in $builds) {
        if (Test-Path -LiteralPath (Join-Path $previous $d)) {
          Move-ToTrash (Join-Path $web $d)
          Move-Tree (Join-Path $previous $d) (Join-Path $web $d)
        }
      }
    } catch { throw "no se pudo devolver la version anterior a web\ (sigue en $previous): $_" }
    Remove-Stash
    Restart-Task "Web"
  }
}
if (-not $ok) { throw "build de la web: fallo (se restauro la version anterior en web\)" }
Write-Output "4/4 arranque de Web y reinicio de Worker"
Restart-Task "Web"
Restart-Task "Worker"
Remove-Stash
Write-Output "Listo."
