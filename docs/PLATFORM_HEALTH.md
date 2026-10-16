# Health de scraping

Página privada: https://www.eseauto.com.ar/app/health. Solo puede acceder la
cuenta autenticada y con email confirmado `jcapurro97@gmail.com`. El servidor
valida nuevamente el usuario antes de leer los datos; ser administrador no
otorga acceso. La tabla del reporte no admite lecturas con claves de navegador.

En el VPS, el timer `automotive-watchdog.timer` ejecuta el chequeo cada 5
minutos (`automotive-watchdog.service`: `python -m tools.watchdog`, que delega
en `tools.platform_health`, como usuario `automotive` desde
`/opt/automotive/worker`). Para mirarlo a mano:

```bash
ssh automotive-vps
cd /opt/automotive/worker
sudo -u automotive /opt/automotive/.venv/bin/python -m tools.platform_health --dry
```

`--dry` consulta y muestra el resultado sin mandar emails ni publicar el reporte.
`--json` muestra los checks como JSON. La tarea vieja de Windows
`\AutoMotive\Watchdog` usa el mismo script.

Configuración del `.env` operativo:

```dotenv
PLATFORM_HEALTH_EMAIL=jcapurro97@gmail.com
PLATFORM_HEALTH_RUN_TIMEOUT_MINUTES=30
PLATFORM_HEALTH_EMPTY_RUNS=3
PLATFORM_HEALTH_EMAIL_QUOTA_PCT=80
```

Reutiliza `RESEND_API_KEY`, `EMAIL_FROM` y `DATABASE_URL`. Las credenciales no
se incluyen en los avisos. El umbral de fallas es
`app_config.collector_failure_alert_after` (3 por defecto).

Detecta fallas por búsqueda, aunque otro target del mismo collector funcione,
corridas que duran más de 30 minutos y búsquedas vencidas por más de dos cadencias
(mínimo 30 minutos). Tres corridas vacías después de obtener resultados en los
últimos siete días generan un aviso de posible rotura del parser; se puede
desactivar con `PLATFORM_HEALTH_EMPTY_RUNS=0`. Las fuentes deshabilitadas y los
targets sin búsquedas activas con acceso vigente no generan falsas alarmas.
También controla la base, el heartbeat del worker y la web.

## Cuota de emails (Resend)

El plan gratis de Resend permite 100 emails por día y 3.000 por mes. Pasado el
límite, Resend rechaza todo con HTTP 429: alertas, mails de plan, links para
entrar de Supabase Auth (salen por el SMTP de la misma cuenta) y estos mismos
avisos. Por eso el chequeo lee `GET https://api.resend.com/usage`, que cuenta
toda la cuenta, y avisa antes:

- `resend:hoy` y `resend:mes` pasan a «Revisar» al llegar a
  `PLATFORM_HEALTH_EMAIL_QUOTA_PCT` (80% por defecto; `0` apaga el chequeo).
  El email dice cuántos se usaron y cuándo se renueva la cuota: la diaria a la
  medianoche UTC (21:00 en Argentina) y la mensual el día que informa Resend
  (el ciclo de la cuenta, no el mes calendario).
- Cuando el uso baja del umbral (se renovó la cuota, cambió el plan o se subió
  el %) llega un segundo email: «ya no está cerca del límite». Subir del 80%
  al 100% no manda otro.
- En un plan pago (Resend informa el límite diario en `null`) solo vigila el
  mes, y el texto deja de recomendar el plan pago: pide revisar si Resend está
  cobrando los emails extra o frenó los envíos.
- `resend:uso` aparece cuando no se puede leer la cuota, y su arreglo manda
  otro email:
  - Key de Sending access (401 `restricted_api_key`): los emails salen, pero
    no hay aviso de cuota. `/usage` necesita **Full access**; la del VPS
    (`RESEND_API_KEY` en `/opt/automotive/.env`) lo es.
  - Key mal, revocada o suspendida (400/401/403): no salen las alertas, los
    mails de plan ni este aviso, así que solo se ve en `/app/health`. Los links
    de Supabase Auth usan su propia key y siguen saliendo.
  - Respuesta con otro formato o un 404: Resend cambió `/usage` y hay que
    adaptar `tools/platform_health.py`.
- Si Resend no responde (red, 5xx o 429), el chequeo conserva el estado
  anterior: un corte no dispara ni cierra un aviso.

Llamar a `/usage` no gasta cuota de emails.

Un incidente manda un email y su recuperación manda otro. Las variaciones del
contador no repiten el aviso. Una recuperación requiere una corrida exitosa;
un nuevo intento todavía en curso no la confirma. Las fallas de envío conservan
el payload y su clave de idempotencia para reintentarlo. El estado se guarda
atómicamente en `logs/platform_health_state.json`; un bloqueo del sistema
operativo impide chequeos simultáneos. No borrar ese archivo para evitar repetir
incidentes ya avisados.

El último chequeo se publica en `platform_health_checks`, protegido por RLS y
sin permisos para usuarios del navegador. La página se actualiza cada 30 segundos
y marca el reporte como desactualizado después de 12 minutos. El monitor depende
de que el timer del VPS siga activo.

Códigos de salida: 0 saludable; 1 problema detectado y chequeo realizado;
2 error de ejecución o envío. Un email aceptado por Resend no confirma entrega:
para probarla, verificar también el evento de entrega del proveedor.
