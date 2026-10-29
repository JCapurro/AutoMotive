# PAR-02 (tramo 1): checklist «Antes de señar» y texto de `much_cheaper` desde 35 %

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** (a) Un bloque «Antes de señar» en la ficha, con botón «Copiar checklist», configurable desde `/admin/config` (`app_config.risk`) y sin ningún link hasta que Juan los cargue. (b) Un texto propio para la red flag `much_cheaper` cuando el aviso está 35 % o más debajo de lo comparable. Diseño aprobado: [2026-10-29-par02-checklist-design.md](../specs/2026-10-29-par02-checklist-design.md). Ítem PAR-02 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md), solo el tramo 1.

**Architecture:** Worker: `red_flags.py` elige entre tres textos con la clave nueva `much_cheaper_verify_pct` (default en `DEFAULT_RED_FLAGS`, así funciona antes o después de la migración); mismo id y severidad, no cambian scores, niveles, guardas ni `SCORING_VERSION`. Web: módulo de datos `web/lib/risk-checklist.ts` (ítems, texto copiable, esquema zod y normalizador de `app_config.risk`), componente cliente `web/components/app/risk-checklist.tsx`, sección nueva en `web/app/app/listings/[id]/page.tsx`, Server Action `trackRiskChecklist` y validación en `validateConfigChange`. Base: una migración de datos (clave nueva en `red_flags` + fila `risk`) y otra, aparte, que suma `risk_checklist_copied` a `admin_decision_metrics`. Sin esquema nuevo, sin RLS nueva, sin lecturas LLM, sin descargas de imágenes.

**Tech Stack:** Python 3.12 (`pytest`, `pythonpath = worker`), Next 16 / React / TypeScript, zod, vitest, Playwright (proyectos `desktop` y `mobile` a 375 px), Postgres con pgTAP.

## Alcance y decisiones aprobadas

Juan aprobó todas las propuestas de «Decisiones que necesita de Juan» del diseño, tal cual:

1. **Tres bandas** con `much_cheaper_verify_pct = 35`: `[25, 35)` texto actual, `[35, 50)` texto nuevo `much_cheaper_verify`, `≥ 50` texto de anticipo actual. Mismo id `much_cheaper`, misma severidad `warning`.
2. **Copy** de `much_cheaper_verify`: «Publicación {pct}% más barata que publicaciones comparables: un precio tan por debajo es motivo para verificar todo antes de señar.» Encabezado de la checklist: «Son controles que conviene hacer vos. Ese Auto no verificó nada de esta publicación.» Ítems con la redacción propuesta del diseño (ver Task 5).
3. **Links oficiales** en `app_config.risk.links`: los carga Juan. Hasta entonces el bloque sale sin links (ningún `<a>` dentro del bloque).
4. **No topear el nivel en `good` desde 35 %.** Cambiaría scores y alertas; sería un diseño aparte. Este plan no toca `scoring.py` ni `price_check.py`.
5. **La checklist es para todos los planes** (sin `plan_feature`).
6. **Colapsada por defecto** (`<details>`), abierta y con una línea de énfasis si la ficha tiene la flag `much_cheaper` o `partial_price_suspect`.
7. **Métricas:** `risk_checklist_copied` entra a `admin_decision_metrics` con migración propia; `risk_checklist_viewed` queda afuera (es pasivo).

Otras decisiones del diseño que se implementan: coherencia de umbrales `much_cheaper_pct < much_cheaper_verify_pct <= anticipo_pct` (validada en `/admin/config` y defendida en el worker); `risk.checklist_enabled` apaga el bloque sin deploy; solo `https://` (máx. 300 caracteres, sin credenciales en la URL, etiqueta no vacía); links con `target="_blank" rel="noopener noreferrer"`; bloque oculto si el aviso está `gone`; eventos solo a la tabla `events` (no a Pixel ni GA); el texto copiado no lleva datos personales ni links.

**Lo que Juan NO aprobó ni aportó (no se inventa, no se escribe en este plan):** textos legales, links oficiales (DNRPA, patentes e infracciones por jurisdicción, VTV, formulario 08), la lista de jurisdicciones, texto de Privacidad/Términos, y cualquier OK para aplicar migraciones o desplegar en producción. Quedan como tareas explícitas de Juan (sección «Tareas de Juan»). La redacción de la línea de énfasis (Task 5) no figura en el diseño: se escribe como borrador y se revisa en el PR.

**Rama:** `claude/par02-checklist`, desde `main` actualizado. **Orden de edición con el resto:** H-01 (PR #50, rama `claude/email-seller-questions`, sin mergear) → X-01 → PAR-03 → PAR-02 tramo 1. Esos tres y este comparten `worker/tests/notification_fixtures.py`, los snapshots de `worker/tests/snapshots/notifications/` y la secuencia de migraciones; PAR-02 no edita `email_html.py` ni `templates.py` (solo lee `MAX_FLAGS` en `templates.py:62`) ni redefine `match_cards` / `search_results` (eso lo hace X-01 y PAR-03 no lo toca). F-03 es independiente. Para evitar conflictos: este plan agrega un caso de fixture nuevo en lugar de editar `OPPORTUNITY` (que H-01 modifica), y la migración de `admin_decision_metrics` parte de la última definición de la función que haya en `supabase/migrations/` al momento de ejecutarla (no de una copia vieja).

**Comandos de prueba** (desde la raíz del repo salvo indicación):

- Worker offline: `python -m pytest worker/tests/test_intelligence.py worker/tests/test_intelligence_copy.py worker/tests/test_notifications_templates.py worker/tests/test_notifications_engine.py -q`; suite completa: `python -m pytest worker/tests -q -m "not db"`.
- Base de prueba (solo `*_test`): `npx supabase db reset` (local) y después `cd worker; python -m tools.test_db; cd ..`; con `$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"` corre `python -m pytest worker/tests/test_intelligence_postgres.py -q`.
- pgTAP: `npx supabase test db` (README; cada archivo corre en una transacción que se descarta).
- Web (desde `web/`): `npx vitest run lib/risk-checklist.test.ts lib/admin-config.test.ts lib/risk-checklist-actions.test.ts`, `npm test`, `npm run typecheck`, `npm run lint`, `npm run e2e` (necesita el stack local, `web/.env.local` con los valores `# local:` y el worker parado, según `docs/PILOT_SETUP.md`).

## Task 0: preparación y lectura obligatoria

- [ ] Leer `web/CLAUDE.md` → `web/AGENTS.md` y, antes de escribir código en `web/`, las guías de `web/node_modules/next/dist/docs/01-app/`: `01-getting-started/05-server-and-client-components.md`, `01-getting-started/07-mutating-data.md`, `02-guides/server-actions.md` y `02-guides/data-security.md`. Esta versión de Next difiere de la conocida: anotar en el PR cualquier convención que cambie lo planeado (por ejemplo, cómo se importa `server-only` desde un módulo compartido con el cliente).
- [ ] Confirmar el estado de las dependencias de orden: `git fetch` y revisar si H-01 (PR #50), X-01 y PAR-03 ya están en `main`. Si no, crear `claude/par02-checklist` desde la rama más avanzada de ese orden y rebasar al mergear. Releer `ls supabase/migrations | tail` en esa base.
- [ ] Crear la rama: `git switch -c claude/par02-checklist`.
- [ ] Fijar los nombres de migración: timestamp **mayor a `20261118130000`** y mayor a las migraciones de X-01 y PAR-03 que existan en la base de trabajo. Propuestos (provisorios): `20261122120000_par02_risk_config.sql` y `20261122120100_par02_decision_metrics_checklist.sql`. Antes de dar por buenos los nombres, releer `max(version)` de producción **solo con OK de Juan** (consulta de lectura; ver «Tareas de Juan»).
- [ ] Correr la línea base y confirmar verde antes de tocar nada: `python -m pytest worker/tests -q -m "not db"` y `cd web; npm test`.

## Task 1: tests de las bandas de `much_cheaper` (rojo)

Files: `worker/tests/test_intelligence.py` (clases `RedFlagTests`, `GuardAndLevelTests`, `ConfigTests`), `worker/tests/test_intelligence_copy.py`.

- [ ] En `RedFlagTests` agregar un helper que devuelva el texto de la flag `much_cheaper` para un `diff_pct` dado (usando `red_flags(...)` como `RedFlagTests.flags`, con `cfg=CFG`) y una tabla de `diff_pct` → texto esperado: 24,9 sin flag; 25 y 34,9 texto de `copy.RED_FLAG["much_cheaper"]`; 35 y 49,9 texto de `much_cheaper_verify`; 50 texto de `much_cheaper_anticipo`. Cada texto con el `pct` formateado como hoy (`f"{diff_pct:.0f}"`).
- [ ] Test de config: con `IntelligenceConfig.from_app_config({"red_flags": {"much_cheaper_pct": 25, "anticipo_pct": 50, "min_km_per_year": 5000, "min_description_chars": 150}})` (la fila actual de producción, sin la clave nueva) `red_flags["much_cheaper_verify_pct"] == 35`; con la clave presente en la base, gana la de la base.
- [ ] Test de coherencia: con `much_cheaper_verify_pct` fuera de `much_cheaper_pct < verify <= anticipo_pct` (por ejemplo 20, 25 o 60, y también `verify == anticipo_pct`) la banda del medio desaparece: 40 % da el texto actual de `much_cheaper` y 55 % el de anticipo, sin excepción.
- [ ] Test de invariancia: para un aviso con `diff_pct` en cada borde, `assess(...)` devuelve el mismo `score`, `level`, ids de flags (en el mismo orden), severidades y `questions` que con el umbral en 25/50 sin la banda nueva (comparar contra una `IntelligenceConfig` con `much_cheaper_verify_pct` igualado a `anticipo_pct`). Cubre que el cambio es solo de texto.
- [ ] En `test_intelligence.py` ajustar `test_every_flag_reads_as_something_to_verify`: el texto nuevo aprobado no contiene «conviene» (dice «motivo para verificar todo antes de señar»). El test debe exigir `conviene` **o** `verificar` en cada texto de `copy.RED_FLAG`, para conservar la intención («se lee como algo a verificar») sin cambiar el texto aprobado. Anotarlo en el PR.
- [ ] Correr `python -m pytest worker/tests/test_intelligence.py -k "RedFlag or Config" -q` y confirmar que fallan por lo esperado (clave y texto inexistentes).

## Task 2: bandas en el worker (verde)

Files: `worker/intelligence/copy.py`, `worker/intelligence/config.py`, `worker/intelligence/red_flags.py`, `supabase/seed.sql`.

- [ ] `copy.py`: sumar `RED_FLAG["much_cheaper_verify"]` con el texto aprobado (placeholder `{pct}`), junto a `much_cheaper` y `much_cheaper_anticipo`. No agregar literales fuera de ese diccionario.
- [ ] `config.py`: `DEFAULT_RED_FLAGS` suma `"much_cheaper_verify_pct": 35`. No tocar `SCORING_VERSION`.
- [ ] `red_flags.py` (hoy `:81-83`): reemplazar la elección binaria por tres bandas. La banda del medio solo existe si `much_cheaper_pct < much_cheaper_verify_pct <= anticipo_pct`; si no se cumple, se usan las dos bandas de siempre. Id, severidad y condición de disparo (`diff_pct >= much_cheaper_pct`) no cambian. Preferir un helper chico y nombrado antes que anidar condiciones.
- [ ] `supabase/seed.sql:58`: sumar `"much_cheaper_verify_pct": 35` al JSON de `red_flags` (el seed es idempotente y no pisa valores ya ajustados).
- [ ] Correr `python -m pytest worker/tests/test_intelligence.py worker/tests/test_intelligence_copy.py -q` y confirmar verde; el lint de `copy.py` (`test_intelligence_copy.py`) cubre el texto nuevo (`FORBIDDEN_TERMS`).

## Task 3: email con la flag nueva (tests primero) y snapshot

Files: `worker/tests/notification_fixtures.py`, `worker/tests/test_notifications_templates.py`, `worker/tests/test_notifications_engine.py`, `worker/tests/snapshots/notifications/opportunity_much_cheaper_verify.txt` (nuevo).

- [ ] No editar `OPPORTUNITY` (lo modifica H-01). Agregar `OPPORTUNITY_MUCH_CHEAPER` armado a partir del payload de `OPPORTUNITY` con `red_flags` = el texto de `copy.RED_FLAG["much_cheaper_verify"].format(pct="40")` (primero) y una flag informativa, y registrarlo en `CASES` con el nombre `opportunity_much_cheaper_verify`.
- [ ] Test (en `test_notifications_engine.py`, junto a los de `flag_texts`): con tres flags (`much_cheaper` severidad `warning` y dos `info`), `flag_texts` devuelve solo 2 y la de `much_cheaper` va primera; el texto de la banda `[35, 50)` cabe en ese límite (`MAX_FLAGS = 2`, `templates.py:62`).
- [ ] Test en `test_notifications_templates.py`: el texto nuevo aparece en el email (texto y HTML) y en Telegram con su `⚠️`, y no contiene términos de `FORBIDDEN_TERMS` (normalizando con `normalize_text`, como el test de copy existente).
- [ ] Generar el snapshot nuevo: `$env:UPDATE_SNAPSHOTS = "1"; python -m pytest worker/tests/test_notifications_templates.py -q` y revisar el diff: **solo** aparece el archivo nuevo; `opportunity.txt`, `new_match.txt`, `price_drop.txt` y `digest.txt` quedan idénticos (si H-01 ya cambió `opportunity.txt`, eso no es de este PR). Correr sin `UPDATE_SNAPSHOTS` y confirmar verde.

## Task 4: migración 1 (datos) y pgTAP

Files: `supabase/migrations/<TS1>_par02_risk_config.sql`, `supabase/tests/par02_risk_config_test.sql` (nuevo), `docs/TECHNICAL_PLAN.md`.

- [ ] Escribir primero `supabase/tests/par02_risk_config_test.sql` (patrón `product_feedback_test.sql`: `begin; select no_plan(); ... rollback`): existe `red_flags.much_cheaper_verify_pct = 35`; las otras claves de `red_flags` (`much_cheaper_pct`, `anticipo_pct`, `min_km_per_year`, `min_description_chars`) no cambiaron; existe `app_config.risk` con `checklist_enabled = true` y `links` con `dnrpa`, `vtv` y `form_08` en `null` y `patentes` / `infracciones` en listas vacías; correr la migración dos veces no cambia nada (idempotente) y no pisa un `much_cheaper_verify_pct` ya ajustado a otro valor ni un `risk` ya editado.
- [ ] Migración con encabezado `--` que cite `docs/BACKLOG_PRODUCTO_2026-10.md`, el ID PAR-02 y el diseño. Contenido: `update public.app_config set value = value || '{"much_cheaper_verify_pct":35}' where key = 'red_flags' and not (value ? 'much_cheaper_verify_pct')` e `insert ... ('risk', '{"checklist_enabled": true, "links": {"dnrpa": null, "patentes": [], "infracciones": [], "vtv": null, "form_08": null}}') on conflict (key) do nothing`. Sin links, sin jurisdicciones y sin texto legal en el SQL. Va sola en su archivo, sin redefinir funciones.
- [ ] Aplicar **solo** en la base local y en `automotive_test`: `npx supabase db reset`, `cd worker; python -m tools.test_db; cd ..`, `npx supabase test db`. **No** aplicar a producción (paso de Juan).
- [ ] Con `TEST_DATABASE_URL` seteado, correr `python -m pytest worker/tests/test_intelligence_postgres.py -q` y confirmar verde (el worker lee `red_flags` con la clave nueva).
- [ ] `docs/TECHNICAL_PLAN.md` (catálogo de eventos, `:715`): sumar `risk_checklist_viewed` y `risk_checklist_copied`. Sin `npm run gen:types`: no hay cambios de esquema.

## Task 5: módulo de datos `web/lib/risk-checklist.ts` (tests primero)

Files: `web/lib/risk-checklist.test.ts` (nuevo), `web/lib/risk-checklist.ts` (nuevo).

- [ ] Tests (vitest, entorno `node`, `lib/**/*.test.ts`):
  - `riskConfig(raw)` normaliza: ausente, `null`, array, forma inválida o `checklist_enabled` no booleano → checklist visible y sin links; un link con otro esquema que `https://` (`http://`, `javascript:`, `data:`, `//host`), con credenciales en la URL (`https://user:pass@host`), de más de 300 caracteres o con etiqueta vacía se descarta sin romper los demás.
  - `RiskConfigInput` (zod) rechaza esos mismos casos con mensaje, acepta `null` por link y listas vacías, y conserva claves desconocidas (patrón `AdminPlanLimitsInput`).
  - `checklistItems(config)`: sin links, ningún ítem trae `links`; con links, `dnrpa` / `vtv` / `form_08` van en su ítem y las listas `patentes` / `infracciones` se anexan como sublista a su ítem.
  - `checklistText(title)`: texto plano con el título del aviso y los ítems con «conviene verificar», **sin links ni datos personales**; título largo o vacío no rompe.
  - `emphasize(flags)`: `true` con id `much_cheaper` o `partial_price_suspect`, `false` sin ellos o con lista vacía.
  - Lint de copy del módulo: lee `web/lib/risk-checklist.ts` y falla si contiene `FORBIDDEN_TERMS` (de `./copy`, con la misma regla de límites de palabra que `copy.test.ts`) o «verificado por Ese Auto», «garantizado», «seguro» (como promesa), «sin riesgo», «certificado». (`copy.test.ts` recorre `app/`, `components/` y `lib/copy.ts`, no `lib/`; por eso el módulo lleva su propio lint.)
- [ ] Implementar el módulo **sin lógica de UI ni `server-only`** (lo importan el cliente, `config.ts` y `admin-config.ts`): constantes de encabezado, de la línea de énfasis (borrador, ver «Alcance») y de los ítems, `RiskConfigInput`, `riskConfig()`, `checklistItems()`, `checklistText()`, `emphasize()`. Ítems (redacción propuesta aprobada, cada uno una frase «conviene verificar…»):
  1. «Conviene verificar el informe de dominio y el informe histórico del vehículo en el registro automotor (DNRPA).»
  2. «Conviene verificar si hay deuda de patentes e infracciones en la jurisdicción que corresponda.»
  3. «Conviene verificar si tiene prenda u otra restricción registrada.»
  4. «Conviene verificar la VTV.»
  5. «Conviene verificar la cédula y el DNI del titular y que coincidan con quien vende.»
  6. «Conviene verificar cómo se hace la transferencia: formulario 08 ante escribano o registro.»
  7. «Conviene ver el auto y los papeles en persona antes de señar por transferencia.»
  Sin afirmar que Ese Auto verificó algo y sin escribir texto legal propio.
- [ ] Correr `cd web; npx vitest run lib/risk-checklist.test.ts` y confirmar verde.

## Task 6: validación en `/admin/config` y lectura en `webConfig()`

Files: `web/lib/admin-config.ts`, `web/lib/admin-config.test.ts`, `web/lib/config.ts`, `web/app/admin/config/page.tsx`.

- [ ] Tests en `admin-config.test.ts` (patrón `pro_offer` / `plan_limits`): `validateConfigChange("risk", value, current)` devuelve un mensaje para un link `http://`, `javascript:`, con credenciales, de más de 300 caracteres o con etiqueta vacía, y `null` para uno válido; sigue exigiendo la misma forma que el valor actual (objeto). `validateConfigChange("red_flags", value, current)` rechaza `much_cheaper_verify_pct` que no cumpla `much_cheaper_pct < verify <= anticipo_pct` (con mensaje claro) y acepta la fila actual y la fila con 35; claves ausentes caen a los defaults del worker (25, 35, 50) en esa comparación. Un valor que ya cumple no cambia su resultado respecto de hoy.
- [ ] Implementar en `admin-config.ts` las dos ramas nuevas de `validateConfigChange` (la de `risk` con `RiskConfigInput`, importada de `risk-checklist.ts`). Sumar etiquetas en `configFieldLabel` para `risk.checklist_enabled` y `risk.links.*` si el panel las muestra por camino.
- [ ] `config.ts`: sumar `"risk"` a la lista cerrada de claves de `webConfig()` y exponer `risk: RiskConfig` normalizado con `riskConfig(values.risk)`. Ajustar el mock de `webConfig` de los tests existentes que lo necesiten (por ejemplo `free-result-limit-page.test.ts`) solo si fallan por la forma nueva.
- [ ] `web/app/admin/config/page.tsx`: pista en `HINTS` para `risk` (`checklist_enabled` apaga el bloque sin deploy; `links` los carga Juan, solo `https://`; sin links el bloque sale sin ellos) y ampliar la de `red_flags` con `much_cheaper_verify_pct` y la regla de coherencia. Sin texto legal.
- [ ] Correr `cd web; npx vitest run lib/admin-config.test.ts lib/admin-config-actions.test.ts lib/admin-config-forms.test.ts` y confirmar verde.

## Task 7: Server Action `trackRiskChecklist`

Files: `web/lib/risk-checklist-actions.test.ts` (nuevo), `web/app/app/listings/actions.ts`.

- [ ] Test (patrón `listing-interactions.test.ts`: `vi.mock` de `@/lib/auth`, `@/lib/events`, `@/lib/supabase/server`): `trackRiskChecklist(42, "viewed")` llama a `track(..., "user-1", "risk_checklist_viewed", { listing_id: 42 })`; `"copied"` registra `risk_checklist_copied`; una `action` fuera de `viewed|copied` o un `listingId` inválido (no entero positivo) se rechaza sin llamar a `track`.
- [ ] Implementar en `listings/actions.ts`, junto a `trackSellerQuestions`: validar con zod, `requireUser()`, `track()` con `{listing_id}`. Sin Pixel ni GA (solo la tabla `events`; RLS: cada usuario registra eventos propios).
- [ ] Correr `cd web; npx vitest run lib/risk-checklist-actions.test.ts` y confirmar verde.

## Task 8: componente `RiskChecklist` (tests primero)

Files: `web/lib/risk-checklist-component.test.ts` (nuevo), `web/components/app/risk-checklist.tsx` (nuevo).

- [ ] Tests con `renderToStaticMarkup` (patrón `free-result-limit-page.test.ts`, mockeando `trackRiskChecklist` y `sonner`) en tres estados: (1) sin links: encabezado fijo, los 7 ítems, **cero `<a>`**, `<details>` sin `open`; (2) con links cargados: «Ver sitio oficial» solo en los ítems con link, `target="_blank"` y `rel="noopener noreferrer"`, sublistas de patentes e infracciones por jurisdicción; (3) con énfasis (`much_cheaper`): `<details open>` y la línea de énfasis. Un link no `https` que llegue al componente no se renderiza.
- [ ] Implementar `web/components/app/risk-checklist.tsx` (`"use client"`), modelo `seller-questions.tsx`: props `listingId`, `title` (nombre del auto), `config` normalizado, `emphasized`. `<details>` con `open` inicial según `emphasized`; botón «Copiar checklist» con `navigator.clipboard.writeText(checklistText(title))` dentro de `try/catch`, `toast.success` / `toast.error` y `void trackRiskChecklist(listingId, "copied")`. `viewed`: una vez por montaje; con el bloque abierto, `IntersectionObserver` al entrar en pantalla; colapsado, al expandirlo (`onToggle`). Sin `IntersectionObserver` disponible, no se registra el evento y no se rompe nada.
- [ ] Correr `cd web; npx vitest run lib/risk-checklist-component.test.ts` y `npm test`; confirmar verde. `lib/copy.test.ts` ya recorre `components/` y debe seguir verde.

## Task 9: integrar en la ficha

Files: `web/app/app/listings/[id]/page.tsx`.

- [ ] Insertar `<Section title="Antes de señar" ...>` con `RiskChecklist` entre «¿Qué le pregunto al vendedor?» (hoy `:256`) y «Histórico de precios», solo si `!gone && cfg.risk.checklist_enabled`. `emphasized={emphasize(flags)}` con los `flags` ya ordenados de la página; `title={name}`; `config={cfg.risk}`. El `hint` de la sección repite que son controles para hacer uno mismo.
- [ ] No tocar `cautious` (`page.tsx:200`) ni `seller_questions.py`: usan el id `much_cheaper`, no el texto.
- [ ] `cd web; npm run typecheck && npm run lint && npm test`.

## Task 10: Playwright (desktop y 375 px)

Files: `web/e2e/risk-checklist.spec.ts` (nuevo), apoyándose en `web/e2e/support/db.ts` y el patrón de `web/e2e/comparables.spec.ts` (alta de usuario con `magicLink`, aviso sembrado, `query()` contra la base local).

- [ ] Test: en la ficha de un aviso con match aparece «Antes de señar» (colapsado); al abrir, están los 7 ítems y el encabezado; con permisos de clipboard concedidos, «Copiar checklist» deja en el portapapeles un texto con «conviene verificar», sin `http` ni el email del usuario, y aparece el toast; hay una fila `risk_checklist_copied` en `events` para ese usuario y aviso; sin links cargados no hay ningún `<a>` dentro del bloque; `expectNoHorizontalScroll` (helper de `acceptance.spec.ts`).
- [ ] Test con `UPDATE app_config SET value = ... WHERE key = 'risk'` (links de prueba **ficticios** `https://example.test/...`, restaurados en `afterEach`): aparecen los «Ver sitio oficial» con `target="_blank"` y `rel` correcto.
- [ ] Test de énfasis: `UPDATE matches SET red_flags = ...` con un flag `much_cheaper` para ese aviso → el bloque abre expandido con la línea de énfasis. Test de apagado: `checklist_enabled = false` → el bloque no está. Test de aviso `gone`: no está.
- [ ] Correr `cd web; npm run e2e -- risk-checklist.spec.ts` en ambos proyectos y confirmar verde; correr también `acceptance.spec.ts` para verificar que la ficha sigue igual.

## Task 11: migración 2 (`admin_decision_metrics`) y pgTAP

Files: `supabase/migrations/<TS2>_par02_decision_metrics_checklist.sql`, `supabase/tests/admin_decision_metrics_test.sql`.

- [ ] Test primero en `admin_decision_metrics_test.sql`: un usuario cuya única actividad es un evento `risk_checklist_copied` cuenta como activo; uno con solo `risk_checklist_viewed` **no** (copiar el patrón de los casos existentes de `seller_questions_copied`). Confirmar que falla antes de la migración.
- [ ] Migración sola en su archivo: `create or replace` de `public.admin_decision_metrics` partiendo de la **última** definición presente en `supabase/migrations/` al momento de ejecutarla (hoy `20261117120000_admin_decision_metrics.sql`; si X-01 u otra la redefinió, partir de esa), cambiando únicamente la lista cerrada de `human_events` (sumar `'risk_checklist_copied'`) y conservando el comentario «only explicit human actions», `security invoker`, `set search_path = ''` y los grants del original. Encabezado `--` con PAR-02 y la decisión 7 aprobada.
- [ ] Aplicar solo en local y en `automotive_test`: `npx supabase db reset`, `cd worker; python -m tools.test_db; cd ..`, `npx supabase test db`. Confirmar que todos los archivos pgTAP (incluidos `admin_decision_metrics_test.sql` y `rls_test.sql`) pasan.
- [ ] Revisar con `git diff` que la función cambió en una sola línea respecto de la definición de partida.

## Task 12: verificación y cierre

- [ ] `python -m pytest worker/tests -q -m "not db"` verde; con `TEST_DATABASE_URL` a `automotive_test`, suite con Postgres verde; `npx supabase test db` verde; `cd web; npm test && npm run typecheck && npm run lint` verde; `npm run e2e` verde en `desktop` y `mobile`.
- [ ] Revisar a mano que no aparezcan términos prohibidos ni promesas («verificado por Ese Auto», «garantizado», «sin riesgo», «certificado») en la ficha ni en el email, y que sin links no haya ningún `<a>` en el bloque.
- [ ] `graphify update .` desde la raíz.
- [ ] Abrir PR de `claude/par02-checklist` a `main` con: resumen, las dos migraciones **sin aplicar en producción**, la nota del ajuste a `test_every_flag_reads_as_something_to_verify`, la línea de énfasis como texto a revisar, y la lista de «Tareas de Juan». Marcar PAR-02 tramo 1 como entregado en `docs/BACKLOG_PRODUCTO_2026-10.md` y en el plan por fases solo al mergear.
- [ ] Sin deploy ni migración en producción ni reinicio del worker hasta que Juan lo pida (ver abajo).

## Tareas de Juan (no las hace Code)

- [ ] OK para consultar `max(version)` de producción antes de fijar los nombres de migración, y OK para aplicar las dos migraciones en producción (transacción + versión exacta, según el procedimiento acordado). Hasta entonces el worker usa el default 35 del código y la web muestra el bloque sin links (`risk` ausente = checklist visible, sin links).
- [ ] OK para desplegar: worker con `wait_idle` previo, web por el flujo habitual.
- [ ] Cargar en `/admin/config → risk.links`, con `https://` y etiqueta, los links oficiales: informe de dominio e histórico (DNRPA), VTV, formulario 08, y patentes e infracciones por cada jurisdicción que quiera listar (la lista de jurisdicciones también la define Juan). Code no investiga ni propone esos links.
- [ ] Aportar cualquier texto legal y la actualización de Privacidad/Términos si corresponde; este plan no incluye ninguno.
- [ ] Revisar la redacción final de los ítems, el encabezado y la línea de énfasis en el PR.
- [ ] Confirmar el valor real de `app_config.red_flags` en producción (el diseño asume que es igual al seed).

## Riesgos y puntos sin verificar

- El rescore actualiza el texto de `matches.red_flags` solo para avisos vistos en los últimos 14 días; los más viejos conservan el texto anterior.
- No se verificó si el rescore puede generar una notificación al cambiar solo el texto (el módulo documenta que solo un match borrado y re-creado alerta).
- No se verificó el valor de `app_config.red_flags` en producción ni si existe otro consumidor de la lista de eventos fuera de SQL.
- `npx supabase test db` corre sobre la base del stack local (transacciones descartadas); el comando contra `automotive_test` con `--db-url` no está documentado en el repo y no se usa.
- La forma final de `admin_decision_metrics` y la numeración de migraciones dependen de lo que mergeen X-01 y PAR-03 antes: por eso las migraciones se nombran y se escriben al final, sobre la base rebasada.
- Entre 35 % y 50 % un aviso puede seguir saliendo «🔥 Alta oportunidad»; el texto nuevo no puede decir «no es una oportunidad» (por eso dice «verificá todo antes de señar»). Topear el nivel queda fuera.

## Rollback

- Web: `risk.checklist_enabled = false` en `/admin/config` apaga el bloque sin deploy; revertir el PR lo quita del código.
- Worker: borrar `much_cheaper_verify_pct` de `app_config.red_flags` (o igualarlo a `anticipo_pct`) devuelve el texto anterior a partir del próximo rescore; con la clave ausente el worker usa 35, así que para volver al texto anterior hay que igualarla a `anticipo_pct`, o revertir el PR.
- Base: las dos migraciones son de datos / `create or replace`; no hay nada que revertir en los datos. La migración 2 se deshace con otro `create or replace` desde la definición anterior, sin `drop`.
