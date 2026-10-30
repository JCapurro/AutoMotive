# Handoff: backlog de producto, Fase 1 (PAR-03 y PAR-02 tramo 1)

Fecha: 2026-10-30. Sesión local de Claude Code en el PC de Juan. Respuestas a Juan siempre en español.

## Objetivo

Implementar el backlog de producto por fases siguiendo `docs/PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md` (en `main`). Juan aprobó todos los diseños ("apruebo todo"), pero **no** aprobó: textos legales, links oficiales (DNRPA, patentes/infracciones, VTV, formulario 08), textos de Privacidad/Términos, ni aplicar migraciones o desplegar a producción. Leer `max(version)` de producción también necesita su OK.

## Qué está hecho

| Ítem | Estado |
|---|---|
| H-01 | PR #50, mergeado |
| X-01 seguimiento | PR #51, mergeado |
| F-03 fase 0 | PR #52, mergeado (`main` = 08d3daa) |
| **PAR-03 por aviso** (días publicado y bajas) | **PR #53 abierto**, rama `claude/par03-dias-y-bajas` (bf23729), base `main` |
| **PAR-02 tramo 1** (checklist «Antes de señar») | **PR #54 abierto**, rama `claude/par02-checklist` (667e5ed), base `claude/par03-dias-y-bajas` |
| Arreglo de tests de base viejos | rama `claude/fix-db-tests` (2335db2), **pusheada en este handoff, sin PR**; base 048ca30 (anterior a `main` actual) |

Esta rama (`handoff/fase1-par03-par02`) es `claude/par02-checklist` + este archivo; no tiene código nuevo.

Las descripciones de #53 y #54 tienen el detalle de cambios, tests y la lista de pendientes de Juan. Los planes con notas de lo que se hizo distinto están en:
- `docs/superpowers/plans/2026-10-29-par03-dias-y-bajas.md`
- `docs/superpowers/plans/2026-10-29-par02-checklist.md`
- Diseño PAR-03: `docs/superpowers/specs/2026-10-29-par03-dias-y-bajas-design.md`

Cada PR pasó por implementación, dos revisores, verificación adversarial de cada hallazgo y corrección de los confirmados.

### Decisiones clave y por qué
- **PAR-02 va encima de PAR-03**: comparten fixtures, snapshots y numeración de migraciones. Mergear #53 primero; GitHub re-apunta #54 a `main`.
- **PAR-03 redondeo**: `listing_price_tracks()` devuelve `cum_pct` a 1 decimal y `cum_usd` a 0, y el worker redondea half-up (`templates.half_up`). Antes Python (banker's) y JS (`toFixed`) mostraban 6,2 % vs 6,3 % para el mismo aviso. El caso 6,25 % / USD 2.500,50 → "-USD 2.501 (-6,3%)" está en pgTAP, pytest, vitest y e2e.
- **PAR-03 helper security definer** `price_track_min_drop_pct()`: `app_config` está revocado para `authenticated`, así que la función security invoker no podía leer el umbral (mismo patrón que `comparables_min_n`).
- **PAR-03 resumen de ficha** siempre en la forma USD aprobada (también en avisos en pesos); tarjeta y mail siguen mostrando pesos para avisos en ARS.
- **PAR-02 banda de texto** de `much_cheaper` se elige con el porcentaje ya redondeado que se muestra (`f"{diff_pct:.0f}"`).
- **PAR-02 eventos**: `risk_checklist_copied` solo tras copia exitosa; `risk_checklist_viewed` solo por IntersectionObserver.
- Copy lint: FORBIDDEN_TERMS se chequea por palabra completa («valer» está permitido).

## Estado actual

**Funciona (verificado en la base local):**
- PAR-03: pgTAP `price_tracks_test` 42/42; pytest offline 2595 passed; Postgres `test_notifications_postgres` + `test_body_type_postgres` verdes; web vitest 647, typecheck, lint; e2e `price-tracks.spec.ts` y `tracking.spec.ts` desktop + 375 px. EXPLAIN con 50k avisos / 200k snapshots: index scan, ~12 ms (50 ids), ~50 ms (200 ids).
- PAR-02: pgTAP `par02_risk_config_test` 7/7, `admin_decision_metrics_test`, `rls_test`; pytest offline 2604 passed; Postgres relacionados 66 passed; vitest 702; e2e `risk-checklist.spec.ts` 10/10.
- CI de GitHub en #53 y #54: solo Vercel Preview Comments, en verde. Auto-fix de la app de escritorio estaba activo en ambos PRs.

**No verificado / falla:**
- La suite completa `pytest -m db` (~23 min) no se corrió en ninguna de las dos ramas.
- Fallos previos y ajenos que siguen en `main`: pgTAP `comparables_test`, `f4_web_test`, `f6_metrics_test` (40-42, max_profiles), `f7_pilot_test`, y 5 tests `-m db` (ingest Telegram ×3, mercadopago, migrate_sqlite) → arreglados en `claude/fix-db-tests`. Además `e2e/acceptance.spec.ts` paso 2 falla (hace `selectOption` sobre «Versiones», que desde 8b7c453 es un menú, no un `<select>`): **sin arreglar**.
- `test_crawl_lanes::test_a_hung_child_is_killed` es flaky en Windows (pidfile vacío).
- El hallazgo "onToggle registra `viewed` al montar" de PAR-02 no se reprodujo en Chromium; el arreglo es defensivo. Firefox/Safari sin probar.

**Producción:** nada tocado. Las migraciones `20261121120000_par03_price_tracks.sql`, `20261122120000_par02_risk_config.sql` y `20261122120100_par02_decision_metrics_checklist.sql` solo están en la base local (y también siguen pendientes en prod las de F-03 y X-01).

## Preguntas abiertas para Juan
1. Aprobar el rótulo «Ver el histórico de precios» (PAR-03, `PRICE_TRACK.historyToggle` en `web/lib/copy.ts`).
2. Aprobar los textos de PAR-02: 7 controles, encabezado, énfasis «Por el precio de esta publicación, conviene hacer todos estos controles antes de señar.», «Controles para hacer vos antes de dejar una seña.», «Ver los controles», «Copiado. Tenelo a mano antes de señar.»
3. Cargar los links oficiales en `risk.links` desde `/admin/config` (https, con rótulo).
4. OK para leer `max(version)` de producción y aplicar migraciones (F-03, X-01, PAR-03 — archivo actual, cambió por el redondeo —, PAR-02).
5. ¿Abrir PR de `claude/fix-db-tests`? Está sobre 048ca30; puede necesitar rebase sobre `main`.
6. Revisar con avisos reales de contado: la baja se calcula sobre el precio publicado y la tarjeta muestra el efectivo.
7. Texto de Privacidad para las notas de X-01.

## Próximos pasos concretos
1. Esperar revisión de Juan en #53; mergear #53, luego #54 (re-apuntado a `main`).
2. Con OK de Juan, en producción: leer `max(version)`; aplicar cada migración en una transacción + `insert into supabase_migrations.schema_migrations(version,name)` con la versión exacta (script guardado del VPS, `sudo -u automotive`, venv del worker). Orden: migración → worker en el VPS (`wait_idle` antes de reiniciar) → web en Vercel.
3. Arreglar `e2e/acceptance.spec.ts` (selector de «Versiones»).
4. Seguir con la Fase 2 de `docs/PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md`. Al mergear, marcar los ítems en el backlog y correr `graphify update`.

## Reglas operativas que no están en el código
- Sin cambios en producción sin OK explícito de Juan. Migración manual en prod = transacción + insert de la versión exacta.
- Puerto 3000 es la web prod legacy en el PC: Playwright nunca debe reusarlo (`reuseExistingServer: false`; chequear que esté libre). En la nube no aplica.
- Nunca crear proyectos Supabase en la org tecc (cuesta US$10/mes). El proyecto hosted es `dnqyravczgcpuowijbja`.
- `web/types/database.ts` se mantiene a mano; no correr `gen:types` sobre él.
- Migraciones nuevas por encima de `20261122120100`.
- Atribución de commits: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Lo que no se pudo pushear (solo local)
- `supabase/.env` (gitignored; hace falta en cada worktree para `npx supabase test db`) y el `local.env` con las claves del stack local de Supabase: secretos, no se commitean. En la nube hay que levantar un stack propio.
- Salidas del EXPLAIN de PAR-03 y el script del workflow: en el scratchpad de la sesión local (`...\Temp\claude\...\scratchpad\par03\`), no en el repo.
- Estado de la base local: tiene aplicadas las migraciones de PAR-03 y PAR-02.
- En el checkout principal (`claude/disenos-fase0-1`) hay cambios sin commitear que **no** son de esta sesión y no se tocaron: `graphify-out/*` modificado y sin trackear `docs/E1_REVIEW.json`, `docs/E1_VERIFY.json`, `docs/E4E5_VERIFY.json`, `docs/E4_REVIEW.json`, `docs/E5_REVIEW.json`, `docs/PLAN_MERCADO_DISENOS.json`, `docs/PLAN_MERCADO_Y_OPORTUNIDADES.md`, `docs/V1V5_VERIFY.json`, `docs/W1W4_VERIFY.json`, `docs/X1X2_VERIFY.json`, `docs/marketing/v1-autos-nuevos-2026-10-19/`, `docs/marketing/v3-asi-lo-arme-2026-10-21/`, `monthly-spend-buddy-38/`. Si hacen falta en la nube, Juan tiene que decidir si se commitean.
