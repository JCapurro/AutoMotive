---
type: "query"
date: "2026-10-09T11:21:06.580812+00:00"
question: "only cars usados y sc clasificados no scrapean correctamente. que logica tienen?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["InstagramScraper", "OnlyCarsUsadosScraper", "SCClasificadosScraper"]
---

# Q: only cars usados y sc clasificados no scrapean correctamente. que logica tienen?

## Answer

Consulta expandida con vocabulario verificado del grafo: instagram, only, cars, clasificados, scraper, caption. Verificado el 2026-10-09 08:18 Argentina: ambas fuentes habilitadas, 7200 segundos de intervalo, 45 fallos consecutivos por Instagram login or verification redirect en /opt/automotive. Ultimo ok 2026-10-08 16:25 Argentina: Only Cars 2 avisos, SC 10. Comparten InstagramScraper, feed reciente hasta 24 posts por defecto, cap 60, seis scrolls y fin tras dos sin novedades. Sin recorrido historico ni OCR. Se verifican autor y shortcode, caption completo, vendido y datos minimos. Un error de transporte o parser puede abortar el lote antes de ingest. Catalogo: Only Cars 20 avisos, 12 sin marca o modelo; SC 11 avisos, 2 sin marca o modelo. Suite offline: 45 passed; el bloqueo operativo sigue abierto. No se cambiaron collectors.

## Outcome

- Signal: useful

## Source Nodes

- InstagramScraper
- OnlyCarsUsadosScraper
- SCClasificadosScraper