<#
  Removes the \AutoMotive\RepairBot scheduled task. A tick already running finishes on its own.
  The bot home (config.json, state, runs, the clone) stays: delete it by hand if wanted.
#>
$folder = "\AutoMotive\"
if (Get-ScheduledTask -TaskPath $folder -TaskName "RepairBot" -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskPath $folder -TaskName "RepairBot" -Confirm:$false
  Write-Output "tarea ${folder}RepairBot eliminada"
} else {
  Write-Output "no hay tarea ${folder}RepairBot"
}
