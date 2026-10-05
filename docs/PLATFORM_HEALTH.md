# Health de scraping

Página privada: https://www.eseauto.com.ar/app/health. Solo puede acceder la
cuenta autenticada y con email confirmado `jcapurro97@gmail.com`. El servidor
valida nuevamente el usuario antes de leer los datos; ser administrador no
otorga acceso. La tabla del reporte no admite lecturas con claves de navegador.

El watchdog ya registrado en Windows ejecuta el chequeo cada 5 minutos:

```powershell
cd C:\Users\Juan\Desktop\AutoMotive\worker
python -m tools.platform_health --dry
python -m tools.platform_health
```

`--dry` consulta y muestra el resultado sin mandar emails ni publicar el reporte.
`--json` muestra los checks como JSON. La tarea existente `\AutoMotive\Watchdog`
sigue usando `python -m tools.watchdog`, que delega en el mismo script.

Configuración del `.env` operativo:

```dotenv
PLATFORM_HEALTH_EMAIL=jcapurro97@gmail.com
PLATFORM_HEALTH_RUN_TIMEOUT_MINUTES=30
PLATFORM_HEALTH_EMPTY_RUNS=3
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
de que la PC esté encendida y la tarea programada pueda ejecutarse.

Códigos de salida: 0 saludable; 1 problema detectado y chequeo realizado;
2 error de ejecución o envío. Un email aceptado por Resend no confirma entrega:
para probarla, verificar también el evento de entrega del proveedor.
