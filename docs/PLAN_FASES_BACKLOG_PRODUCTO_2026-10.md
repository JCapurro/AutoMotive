# Plan por fases del backlog de producto

Fecha: 29/10/2026. Deriva de [BACKLOG_PRODUCTO_2026-10](BACKLOG_PRODUCTO_2026-10.md) (26/10) después de verificar cada afirmación de «Qué existe» contra el repo (HEAD 048ca30) y cruzar dependencias, archivos compartidos y migraciones.

Estado: **propuesta para que Juan la revise**. No hay nada implementado, ninguna migración aplicada y nada tocó producción. Cada fase se ejecuta como indica el backlog: diseño corto en `docs/superpowers/specs/`, aprobación de Juan, plan en `docs/superpowers/plans/`, rama `claude/<slug>`.

## 1. Qué cambia respecto del backlog

El orden general del backlog se sostiene, pero la verificación encontró seis problemas que obligan a reordenar:

1. **F-03 está subestimada y bloquea más de lo que parece.** `listings` no tiene columna de provincia (solo `location_text`, `lat/lon`, y `normalization/geo.py` no devuelve provincia). Además PAR-03 (bloque del modelo), PRO-02 (rotación) y PRO-04 necesitan unas 4 semanas de datos acumulados. Hay que arrancarla ya, en paralelo, solo con provincia y la tabla con el job en dry-run.
2. **F-02 y PRO-02 no son «M» chicos.** El CHECK de `listings.seller_type` solo admite `private|dealer`, `ingest.py` pisa `seller_type` en cada reingesta (una inferencia nocturna se perdería) y hay unos 8 consumidores que asumen dos valores. La inferencia debe vivir en un atributo o columna aparte. Mardel e Instagram dejan el vendedor en null, así que hay que medir cobertura antes de comprometer PRO-02 (exige `dealer_n ≥ 5`).
3. **El umbral de 35 % de PAR-02 no existe.** Hoy `app_config.red_flags` tiene 25 y 50; hay que crear la clave.
4. **H-01 no es cortar «las 3 primeras».** `matches.seller_questions` es un solo texto de WhatsApp (saludo + preguntas), y el payload de notificación no lo trae. Hace falta una función que devuelva la lista y traerla en la query.
5. **Varias referencias del backlog no existen:** `search_profiles.location_label`, `web/public/`, `search_profiles.kind`, `plan_limits.pro.min_threshold_usd`, `gone_at`. `llm_jobs.user_id` es NOT NULL, así que un job de sistema para PAR-04 no encaja sin otra tabla. `profiles.default_channels` tiene un CHECK que rechaza `push`.
6. **PRO-03 contaría contra el plan.** `enforce_plan_limits`, `search_access_active` y `dashboard_summary` cuentan todos los `search_profiles` activos; hay que excluir `stock_watch` en cada uno.

También se confirmó: X-01 está más avanzado de lo dicho (`setStatus()` ya acepta `contacted` y `visit_scheduled`, falta UI y nota); el orden «por costo total» de PAR-01 es riesgoso (reescribe `search_results`, que ya se redefinió 3 veces).

## 2. Fases

Tamaños: S ≤ 1 día, M 2–3, L 4–6. Una fase termina cuando sus piezas están en `main` con tests; aplicar a producción siempre requiere OK de Juan.

### Fase 0 · Arranque en paralelo de F-03 (archivos nuevos, casi no choca)

| Pieza | Capa | Tamaño |
|---|---|---|
| Provincia/zona por aviso (derivada de lat/lon o texto) | db + worker | M |
| `market_stats` + `app_config.market_stats` + job `python -m tools.market_stats --dry-run`, solo oferta y precios | db + worker | M |
| Después: `drop_share` y `median_total_drop_pct`; luego `demand_count` con piso de privacidad | worker | S + M |

Sin UI ni gating. El objetivo es acumular semanas. Aviso: las semanas anteriores no se reconstruyen bien (ML estuvo sesgado antes del 24/10).

### Fase 1 · Entregas baratas e independientes (no tocan `comparables()`)

Orden estricto en `email_html.py`/`templates.py`: H-01 → PAR-03.

| Orden | Ítem | Entrega |
|---|---|---|
| 1 | H-01 | Función de lista de preguntas, query de notificaciones, bloque en el email, snapshots con y sin preguntas. Mínimo: corregir la landing (1 línea) |
| 2 | X-01 | (a) Selector de estado + nota en la ficha (solo web); (b) `match_cards`/`search_results` con nota y filtro por estado |
| 3 | PAR-03 (por aviso) | Días publicado, bajas y baja acumulada en ficha y tarjeta; luego email y digest. Sin bloque del modelo |
| 4 | PAR-02 tramo 1 | Checklist «Antes de señar» + copy de `much_cheaper` ≥ 35 % (crear la clave). Sin pHash |

### Fase 2 · Vendedor, filtro, margen y costo

| Orden | Ítem | Entrega |
|---|---|---|
| 1 | F-02 | (1) Vista `seller_listing_count` + métrica admin de % null por fuente, sin cambio visible. (2) `dealer_inferred` en atributo aparte («posible agencia»). (3) `price_ref` con medianas por tipo. Cada paso se puede frenar |
| 2 | PRO-01 (sin push) | `contact_template` + mensaje listo en ficha; filtro duro `seller_types` (Pro) con «no informado» explícito; bloque en el email |
| 3 | PRO-02 | (a) `margin_ref` + copy en ficha; (b) tarjeta, email Pro y orden por margen; (c) umbral en USD (toca el camino de emails inmediatos) |
| 4 | PAR-01 | Migración con parámetros en null → Juan los carga → módulo de cálculo con resultado parcial → ficha, tarjeta y email. **Sin orden por costo total en v1** |

Un solo bump de `SCORING_VERSION` por deploy (un único rescore masivo; evita mails duplicados).

### Fase 3 · Push, riesgo completo, modelo y guías

| Orden | Ítem | Entrega |
|---|---|---|
| 1 | F-04 | PWA + suscripción + Ajustes sin envío; luego `channels/push.py` con endpoint falso; luego activación para Pro con respaldo email |
| 2 | PRO-01 push | Canal por búsqueda, solo si F-04 lo justifica |
| 3 | PAR-02 resto | pHash + `duplicate_photos`, `private_many_listings` (tras F-02), `cross_source_duplicate` con backfill |
| 4 | PAR-03 bloque del modelo + PRO-02 rotación | Ya con 4+ semanas de `market_stats`; gating `model_stats` |
| 5 | PAR-04 | En cualquier hueco y en paralelo: tabla + prompt + panel admin con 5 guías piloto → páginas `/guias` + sitemap → preguntas en `seller_questions` |

### Fase 4 · Validación comercial primero

Orden cambiado: PRO-04 pasa antes porque depende solo de F-03.

F-01 (solo cuando exista consumidor) → PRO-04 → PAR-05 (a: `/vender` sin captación; b: email opt-in; c: consentimiento + lead) → PRO-03 (gate: 3 Pro con stock manual) → PRO-05 (gate: captación efectiva de PAR-05).

## 3. Cadena de migraciones

Toda migración debe ser mayor a `20261118130000` y hay que releer `max(version)` de producción antes de nombrarla. Las que redefinen funciones grandes (`comparables`, `match_cards`, `search_results`, `enforce_plan_limits`) van solas, con su pgTAP.

1. Provincia + `market_stats` (Fase 0)
2. X-01 y PAR-03: `match_cards`/`search_results` (fusionar o encadenar sin pisar, partiendo de `20261030120000` + free cap)
3. PAR-02 tramo 1: umbral de `much_cheaper`
4. F-02: CHECK/atributo, `seller_listing_count`, `app_config.seller_classification`, `price_ref`
5. PRO-01: `contact_template`, `plan_limits.pro.seller_filter`, eventos en `admin_decision_metrics`
6. PRO-02: `margin_ref`, `opportunity_threshold_usd`, `app_config.dealer_margin`
7. PAR-01: `app_config.cost_estimator`
8. F-04: `push_subscriptions`, nuevo CHECK de `default_channels`, `app_config.push`
9. PAR-04: `model_guides`, CHECK de `llm_jobs.kind`, solución al `user_id` NOT NULL
10. F-01, PAR-05, PRO-05, PRO-03, PRO-04

Pendiente de resolver antes de PAR-04: `20261107130000_timing_chain_catalog.sql` sigue NOT APPLIED.

## 4. Conflictos de archivos (qué serializar)

- `email_html.py` + `templates.py` + snapshots: H-01 → PAR-03 → PRO-01 → PRO-02 → PAR-01 → PAR-02.
- `comparables()` / `PriceRef`: F-02 → PRO-02 → F-01.
- `match_cards` / `search_results`: X-01 → PAR-03 → PRO-02.
- `matching.py` + copy + formularios: F-02 decide la semántica de `dealer_inferred` antes de PRO-01.
- `engine.py` / `SCORING_VERSION`: un solo bump por deploy.
- `seller_questions.py`: H-01 → PRO-01 → PAR-04.
- `notifications/engine.py` + `service.py`: PRO-02 → PAR-02; F-04 no en paralelo con PRO-02.
- `lib/pro.ts`, `admin-config.ts`, `config-forms.tsx`: choque menor y constante; agregar las claves en un mismo PR por fase.
- Paralelizables: X-01 con H-01, F-03 con todo, PAR-04 con casi todo, PWA de F-04 con la web de PRO-01.

## 5. Decisiones y valores que solo Juan puede dar

**Antes de la Fase 0/1**
- Que F-03 arranque ya; granularidad de zona (provincia o región); `min_n` (8 precios, 5 días), banda de 2 años, semana ISO.
- H-01: sumar preguntas al email o corregir la landing; cuántas y si se omite el saludo.
- X-01: solo Pro o todos (habilitar la UI mueve la métrica `v_validation_criteria`).
- PAR-02: links oficiales (DNRPA, patentes e infracciones por jurisdicción, VTV, formulario 08), texto de la checklist y copy de `much_cheaper` ≥ 35 %.

**Antes de la Fase 2**
- F-02: `dealer_min_listings` (4) y ventana (30 días); si `dealer_inferred` cuenta como dealer en filtros y aviso de gastos; copy «posible agencia».
- PRO-01: voz del mensaje, largo de la plantilla, filtro duro solo Pro y qué pasa con la preferencia blanda actual.
- PRO-02: % y mínimo de acondicionamiento, `min_threshold_usd`, OK al bump de `SCORING_VERSION`.
- PAR-01: cargar en `/admin/config` transferencia, sellado, gastos fijos, gestoría y patente (CABA, Buenos Aires, resto) con fecha y fuente; qué hacer con el aviso fijo 8–10 %.

**Antes de la Fase 3**
- F-04: OK para generar claves VAPID y cargarlas en Vercel Production y en el `.env` del VPS; plan por defecto; cuenta o búsqueda; `push.max_failures`; nombre e íconos de la PWA; Términos y Privacidad por guardar suscripciones.
- PAR-02: sumar Pillow/imagehash al VPS; política de descarga de imágenes (Facebook); tolerancias y tope diario.
- PAR-04: proveedor LLM y tope propio; aplicar `timing_chain`; tono «Guía orientativa»; revisión de las 30 guías.

**Antes de la Fase 4**
- Validación comercial de PAR-05 y PRO-03; `min_demand_n` (3) y privacidad de `demand_count`; `ttl_days` (45), texto del segundo consentimiento, nombre de `/vender`; `stock.cheaper_pct` (sin valor propuesto); PRO-04 dentro de Pro o Pro+; Términos y Privacidad revisados antes de PAR-05 y PRO-05.

**Transversal:** OK explícito para cada migración en producción (transacción + versión exacta + `max(version)`), `wait_idle` antes de reiniciar el worker, y aprobación de todo cambio que mueva scores.

## 6. Registro de decisión

- [ ] Juan aprueba el reordenamiento (Fase 0 en paralelo, X-01 y PAR-02 tramo 1 en la Fase 1, PRO-04 antes de PRO-03).
- [ ] Juan elige el primer ítem y se abre su diseño en `docs/superpowers/specs/`.
- [ ] Juan responde las decisiones de la Fase 0/1.

## 7. Estado de la Fase 0 y la Fase 1 (30/10/2026)

Código: H-01 (#50), X-01 (#51), F-03 fase 0 (#52) y PAR-03 por aviso (#53) en `main`. PAR-02 tramo 1, la corrección de PAR-03 para avisos de contado o anticipo (opción B), el e2e de aceptación, las migraciones aplicables desde cero y Privacidad de notas en #56. Tests de base al día en #57.

Producción (leído el 30/10): `max(version)` = `20261118130000`. Faltan, en este orden, cada una en una transacción con el insert de su versión exacta:

1. `20261027145911_admin_config_audit.sql`: nunca se aplicó; sin ella `/admin/config` no puede guardar (`admin_update_setting` no existe). Es independiente de las posteriores.
2. `20261119110000_f03_market_stats.sql`
3. `20261119120000_x01_tracking.sql`
4. `20261119130000_x01_outcome_metric.sql`
5. `20261121120000_par03_price_tracks.sql`
6. `20261122120000_par02_risk_config.sql`
7. `20261122120100_par02_decision_metrics_checklist.sql`

Después: worker en el VPS (`wait_idle` antes de reiniciar) y, por último, cargar `risk.links` desde `/admin/config`. La web de `main` ya tolera la base vieja: sin las migraciones, X-01 cae a «Todos», PAR-03 no muestra bajas y el checklist se ve sin links.
