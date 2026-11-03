# Validación comercial de la Fase 4: radar y monitor hechos a mano

Herramientas de la Prueba A (doc «Validación comercial de la Fase 4»). Todo es de solo lectura sobre la base.

| Archivo | Para qué |
| --- | --- |
| `radar.sql` | Los 10 modelos de una zona que más dejaron de publicarse en la semana (`market_stats`, F-03), con precio y el partido más barato. Reemplazar `:week` y `:zone`; devuelve un JSON. |
| `radar_pdf.py` | Arma el PDF de 1 página: `python radar_pdf.py datos.json amba 2026-10-26 radar.pdf "Agencia"`. `datos.json` = lista de `{zone, rows}` con las filas de `radar.sql`. |
| `monitor.sql` | Compara el stock de una agencia contra avisos activos parecidos de su zona (marca y modelo, año ±1, km ±25 %, últimos 30 días) y busca uno más barato aparecido en los últimos 4 días. |
| `monitor_xlsx.py` | Plantilla de la planilla compartida: `python monitor_xlsx.py planilla.xlsx "Agencia"`. |

Reglas de los textos: «dejó de publicarse», nunca «vendido»; precios publicados, no de venta; sin promesas de ganancias.
Los nombres de las agencias y sus planillas no van al repo.
