# Renueva la sesión de Facebook del worker en un paso (Juan, 05/11/2026).
#
# Abre el túnel SSH al VPS con ops/vps/fb-login.sh en una ventana propia,
# espera a que noVNC conteste y abre el navegador en la ventana de login.
# Vos solo iniciás sesión en Facebook: la sesión se guarda sola cuando
# sobrevive a una recarga. Cerrá la ventana del túnel (o Ctrl+C) al terminar.
#
# Uso: doble clic en ops\fb-renovar.cmd, o desde PowerShell:
#   powershell -ExecutionPolicy Bypass -File ops\fb-renovar.ps1

$ErrorActionPreference = "Stop"
$port = 6080
$url = "http://localhost:$port/vnc.html?autoconnect=1&resize=scale"

function Test-NoVnc {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/vnc.html" -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch { return $false }
}

if (Test-NoVnc) {
    Write-Host "El túnel ya está abierto: abro el navegador."
    Start-Process $url
    exit 0
}

Write-Host "Abriendo el túnel al VPS (se abre otra ventana; dejala abierta)..."
$tunnel = Start-Process -FilePath "ssh" -PassThru -ArgumentList @(
    "-t", "-o", "ConnectTimeout=20", "-o", "ExitOnForwardFailure=yes",
    "-L", "${port}:127.0.0.1:$port", "automotive-vps",
    "sudo bash /opt/automotive/ops/vps/fb-login.sh"
)

$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    if ($tunnel.HasExited) {
        Write-Host ""
        Write-Host "El túnel se cerró antes de tiempo (código $($tunnel.ExitCode))." -ForegroundColor Red
        Write-Host "Si dice 'Connection timed out', el VPS no deja entrar desde esta conexión."
        Read-Host "Enter para cerrar"
        exit 1
    }
    if (Test-NoVnc) {
        Write-Host "Listo: abro la ventana de login. Iniciá sesión en Facebook ahí."
        Start-Process $url
        exit 0
    }
    Start-Sleep -Seconds 2
}

Write-Host "noVNC no contestó en 2 minutos. Mirá la ventana del túnel por el error." -ForegroundColor Red
Read-Host "Enter para cerrar"
exit 1
