<# Removes the \AutoMotive\ scheduled tasks and stops their processes (F7, punto 8). #>
$folder = "\AutoMotive\"
Get-ScheduledTask -TaskPath $folder -ErrorAction SilentlyContinue | ForEach-Object {
  Stop-ScheduledTask -TaskPath $folder -TaskName $_.TaskName -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskPath $folder -TaskName $_.TaskName -Confirm:$false
  Write-Output "tarea $folder$($_.TaskName) eliminada"
}
# The supervisors' children (next start, python main.py) outlive the task.
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "run-forever\.ps1|main\.py|next start" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
