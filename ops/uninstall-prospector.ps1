<#
  Removes the \AutoMotive\Prospector scheduled task. A run already going finishes on its own.
  %LOCALAPPDATA%\EseAuto\prospeccion (reports, phone cache, contacted list) stays.
#>
$folder = "\AutoMotive\"
if (Get-ScheduledTask -TaskPath $folder -TaskName "Prospector" -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskPath $folder -TaskName "Prospector" -Confirm:$false
  Write-Output "tarea ${folder}Prospector eliminada"
} else {
  Write-Output "no hay tarea ${folder}Prospector"
}
