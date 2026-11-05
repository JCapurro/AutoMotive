# Ritmo de lectura de Facebook (05/11/2026)

## Por qué

La sesión de Facebook del VPS duraba menos cuanto más se la usaba. Datos de `collector_runs` en producción:

| Sesión desde | Lecturas por hora | Duró |
|---|---|---|
| 19/10 | 5 | 48 h |
| 21/10 | 21 | 7 días |
| 29/10 | 65 | 3,5 días |
| 02/11 | 98 | 17 h |
| 03/11 | 54 | 5 h |
| 04/11 | 97 | 2 h 20 min |

- **Por qué subieron las lecturas:** Facebook pasó de 3 a 85 búsquedas activas, leídas cada 30 minutos las 24 horas.
- **Picos después de renovar:** cada renovación largaba todas las búsquedas atrasadas juntas.
- **Rendimiento:** solo un 6 % de las lecturas trae algún aviso nuevo, y entre la 1 y las 7 baja a un 1–2 %.

Juan aprobó los tres frenos el 05/11. Ninguno garantiza que la sesión dure: Facebook no permite la lectura automática de Marketplace.

## Los tres frenos

1. **Intervalo de 3 horas.** `sources.crawl_interval_seconds` de `facebook` pasó de 1800 a 10800. Es un cambio en la base de producción, aplicado el 05/11.
2. **Tope por hora.** `SOURCE_RUNS_PER_HOUR` (`.env` del worker, por defecto `facebook=25`): una lectura cada 3600/25 = 144 segundos como mínimo. Lo atrasado se reparte en vez de salir todo junto ([worker/pipeline/pacing.py](../worker/pipeline/pacing.py)).
3. **Pausa de noche.** `SOURCE_QUIET_HOURS` (por defecto `facebook=1-7`): no hay lecturas de 1:00 a 6:59, en hora de Argentina (`PACING_TZ`).

Para apagar un freno, dejá la variable vacía en el `.env` del worker. Formato: `fuente=valor` separados por comas, por ejemplo `facebook=25,kavak=60`.

El espaciado del tope vive en memoria: después de reiniciar el worker, la primera lectura sale enseguida.

## Qué medir

En `collector_runs` (source `facebook`):
- cuántas horas dura cada sesión, hasta el primer `session expired (logged out, no c_user cookie)`;
- las lecturas por hora;
- los avisos nuevos por día, comparados con los ~550 por día del 30/10 al 02/11.
