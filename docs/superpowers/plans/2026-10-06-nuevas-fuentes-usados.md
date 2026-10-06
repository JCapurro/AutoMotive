# Nuevas fuentes de usados — Implementation Plan

**Goal:** Agregar Only Cars Usados, SC Clasificados, Mardel Usados, Rosario Garage y Usados Santa Fe al worker, con pruebas de sus contratos y búsqueda de agencias adicionales.

**Architecture:** Mantener `Listing`, normalización, deduplicación y alertas existentes. Mardel, Santa Fe e Instagram recorren un catálogo/feed por fuente; Rosario utiliza los filtros públicos por modelo y categoría. Los bloqueos o cambios de HTML fallan visiblemente y no indican bajas. Instagram comparte transporte con sesión local opcional y parsers de captions; se activa únicamente cuando se valida una lectura real.

**Tech Stack:** Python, httpx, BeautifulSoup, Playwright, pytest; PostgreSQL/Supabase mediante migración idempotente.

## Contratos y alcance

- IDs: `onlycarsusados`, `sc_clasificados`, `mardelusados`, `rosariogarage`, `usadossantafe`.
- Capturar título, moneda/precio real, año/km, ubicación, fotos, descripción y vendedor cuando la publicación lo aporta. No inventar datos ni tomar anuncios recomendados como ficha solicitada.
- Excluir motos/náutica y publicaciones explícitamente vendidas. Precio de consulta o placeholder se conserva como desconocido.
- Sin ejecutar migraciones ni ingesta en producción, ni publicar código: entregar implementación local comprobada y pasos de activación.

## Tasks

- [x] 1. Crear rama aislada; inspeccionar HTML público y contratos de collectors/crawl. Ejecutar baseline `python -m pytest tests/test_parsers.py tests/test_normalization_v2.py` desde `worker/`.
- [x] 2. Implementar `worker/collectors/mardelusados.py`, `usadossantafe.py`, `rosariogarage.py` e `instagram.py`; helpers mínimos compartidos. Guardar fixtures recortados y sin contactos en `worker/tests/fixtures/html/`; pruebas de campos, descuentos, vendido, bloqueo y ficha equivocada en `test_regional_sources.py` y tests específicos de transporte.
- [x] 3. Registrar collectors en `worker/collectors/__init__.py`, configurar sesión IG en `worker/config.py` y `.env.example`, adaptar CLI a los nuevos hosts y captura manual de sesión. Fuentes de catálogo comparten target sin hints de modelo; actualizar `worker/pipeline/crawl.py` y `worker/db/repos/targets.py` más pruebas de agrupación y elegibilidad SQL.
- [x] 4. Añadir migración generada por CLI `supabase/migrations/20261006141335_regional_sources.sql` y seed sin sobrescribir configuración existente. Las cinco habilitadas en nuevas instalaciones después de validar lectura pública. Documentar comandos, cadencias, alcance y activación en `docs/FUENTES_REGIONALES.md`.
- [x] 5. Probar catálogo y detalle en vivo para los tres sitios y lectura de IG; registrar cantidades y límites reales. Ejecutar `python -m pytest -m "not db"`; revisar diff y actualizar grafo con `graphify update .`. 548 pruebas sin DB y 9 de integración pasaron; un fallo legacy de Telegram se reprodujo en el baseline sin cambios.
- [x] 6. Verificar webs oficiales de grandes agencias, ejemplos de ficha y paginación; guardar informe en `docs/research/AGENCIAS_USADOS_2026-10-06.md` con prioridades y URLs. Entregar estado local/producción y limitaciones comprobadas.

## Decisiones de operación

Un target de inventario usa `make=model=NULL` y `query.inventory=true`; la elegibilidad se comprueba contra perfiles con acceso vigente que incluyan la fuente. Los filtros de cada usuario se aplican posteriormente, sin omitir vehículos por los filtros de otro usuario. Si falla una página paginada se registra error, evitando confundir cobertura incompleta con una lectura sana.

## Validation

Pruebas offline de precio, identificadores, monedas, categorías, sold/login wall, páginas repetidas y fallos HTTP. Probes HTTP públicos no escriben en base ni envían notificaciones. Verificar que el HTML conservado permite reparsear las fichas. El push, migración de producción y despliegue requieren una solicitud posterior.
