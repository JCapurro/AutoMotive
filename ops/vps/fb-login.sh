#!/usr/bin/env bash
# Renueva la sesión de Facebook del worker iniciando sesión DESDE el VPS.
#
# Facebook revoca una sesión la primera vez que se usa desde otra IP que la
# del login (2026-10-17: una sesión creada en la PC murió en su primer pedido
# desde el VPS). Por eso el login se hace acá, en un Chromium visible dentro de
# un escritorio virtual (Xvfb) que se ve desde el navegador de la PC con noVNC.
# Todo escucha solo en 127.0.0.1: se entra por el túnel SSH y nada queda
# expuesto a internet. Al terminar (o con Ctrl+C) se apaga todo.
#
# Desde la PC (una sola línea):
#   ssh -t -L 6080:127.0.0.1:6080 automotive-vps "sudo bash /opt/automotive/ops/vps/fb-login.sh"
# y abrir http://localhost:6080/vnc.html?autoconnect=1&resize=scale
#
# No hace falta reiniciar el worker: lee fb_state.json en cada corrida.
set -euo pipefail

APP=/opt/automotive
RUN_AS=automotive
DISPLAY_NUM=:77
VNC_PORT=5977
WEB_PORT=6080

if [ "$(id -u)" -ne 0 ]; then
  echo "Correlo como root (sudo)." >&2
  exit 1
fi
if ! command -v websockify >/dev/null || [ ! -f /usr/share/novnc/vnc.html ]; then
  echo "Instalando noVNC y websockify (una sola vez)..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends novnc websockify >/dev/null
fi
for bin in Xvfb x11vnc; do
  command -v "$bin" >/dev/null || { echo "Falta $bin (apt-get install xvfb x11vnc)" >&2; exit 1; }
done

pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sudo -u "$RUN_AS" Xvfb "$DISPLAY_NUM" -screen 0 1366x900x24 -nolisten tcp >/dev/null 2>&1 &
pids+=($!)
sleep 1
sudo -u "$RUN_AS" x11vnc -display "$DISPLAY_NUM" -localhost -rfbport "$VNC_PORT" -nopw -forever -shared -quiet >/dev/null 2>&1 &
pids+=($!)
sudo -u "$RUN_AS" websockify --web /usr/share/novnc "127.0.0.1:$WEB_PORT" "127.0.0.1:$VNC_PORT" >/dev/null 2>&1 &
pids+=($!)
sleep 1

echo
echo "Abrí en la PC:  http://localhost:$WEB_PORT/vnc.html?autoconnect=1&resize=scale"
echo "Iniciá sesión en Facebook en esa ventana; se guarda sola al llegar a la home."
echo

cd "$APP/worker"
sudo -u "$RUN_AS" env DISPLAY="$DISPLAY_NUM" "$APP/.venv/bin/python" -m collectors.facebook --auto
