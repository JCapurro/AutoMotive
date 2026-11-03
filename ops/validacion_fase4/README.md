# Validación comercial de la Fase 4: radar y monitor hechos a mano

Herramientas de la Prueba A (doc «Validación comercial de la Fase 4»). Todo es de solo lectura sobre la base.
Lo que se manda a las agencias es una imagen PNG por WhatsApp. No se usan planillas compartidas (decisión de Juan, 03/11).

| Archivo | Para qué |
| --- | --- |
| `radar.sql` | Los 10 modelos de una zona que más dejaron de publicarse en la semana (`market_stats`, F-03), con precio y el partido más barato. Reemplazar `:week` y `:zone`; devuelve un JSON. |
| `monitor.sql` | Compara el stock de una agencia (en `stock`, cargado a mano a partir de lo que manda por WhatsApp) contra avisos activos parecidos de su zona: marca y modelo, año ±1, km ±25 %, últimos 30 días. Busca también uno más barato aparecido en los últimos 4 días. |
| `imagenes.mjs` | Arma la imagen de 1080 px de ancho: `node imagenes.mjs radar radar.json amba 2026-10-26 radar.png "Agencia"` o `node imagenes.mjs monitor monitor.json 2026-11-18 stock.png "Agencia" amba`. Usa Playwright. |

Reglas de los textos: decir «dejó de publicarse», nunca «vendido»; son precios publicados, no de venta; sin promesas de ganancias.
Los nombres de las agencias, su stock y las imágenes no van al repo.
