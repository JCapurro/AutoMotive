# PAR-02 (resto) · `private_many_listings`, `cross_source_duplicate` y `duplicate_photos` con pHash

Ítem del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) (PAR-02, sección «Señales de riesgo y checklist antes de señar») y fila 3 de la Fase 3 del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md). El tramo 1 (checklist «Antes de señar» y copy de `much_cheaper`, [spec](2026-10-29-par02-checklist-design.md)) ya está en producción. Fecha: 2026-11-02. Estado: **borrador para que Juan lo apruebe**; nada implementado, ninguna migración escrita ni aplicada.

Alcance: tres señales nuevas en «Conviene verificar» (ficha) y en el email de oportunidad, el cálculo de hashes perceptuales de fotos (**apagado por defecto**), un orden de prioridad de red flags configurable, el evento `duplicate_link_clicked` y un backfill. Ninguna señal mueve el score ni el nivel, no hay bump de `SCORING_VERSION` y nada notifica por sí solo. Política vigente: Ese Auto no contacta vendedores, no afirma haber verificado nada y no promete detección certificada; todo se redacta como «conviene verificar / conviene preguntar / conviene comparar».

Antes de tocar `web/`: leer `web/AGENTS.md` y la guía correspondiente en `web/node_modules/next/dist/docs/` (Next 16).

## Qué existe hoy (verificado en el repo, `origin/main` = `c354c13`)

- **Red flags.** `worker/intelligence/red_flags.py` es puro: `red_flags(listing, diff_pct, guard, timing_belt, cfg, now)` devuelve `RedFlag(id, text, severity)`; textos en `copy.RED_FLAG`. `intelligence/engine.assess` las calcula por (aviso × búsqueda) y se guardan armadas en `matches.red_flags` (`Evaluation.row`). La fila del aviso viene de `db/repos/listings.rows_for_scoring` (`SELECT l.*` + catálogo), así que cualquier columna de `listings` o dato que esa consulta sume llega a las reglas.
- **Orden.** No hay orden en `app_config.red_flags` (corrección 2 del spec del tramo 1). El email usa `notifications/service.flag_texts`: `sorted(severity != "warning")` estable y corta en `templates.MAX_FLAGS = 2`. La ficha (`web/app/app/listings/[id]/page.tsx:111`) ordena igual y muestra todas. El orden efectivo hoy: warnings en orden de emisión (`much_cheaper`, `partial_price_suspect`) y después las info en orden de emisión (`no_owners`, `service_unavailable`/`no_service`, `timing_pending`/`no_timing_belt`, `short_description`, `damage_mentioned`, `commercial_use`, `vtv_pending`, `low_km_for_age`, `repost`, `price_mismatch`, `year_mismatch`, `km_mismatch`).
- **Actualización del texto guardado.** El rescore periódico re-evalúa matches de avisos vistos en 14 días; F-02 además re-puntúa en el momento los avisos cuya inferencia cambió (`pipeline/seller_classification._rescore`). Re-puntuar no notifica.
- **F-02.** `listings.seller_key`, `seller_listing_count` (autos distintos del mismo `(source, seller_key)` publicados en 30 días y activos) y `dealer_inferred` («posible agencia»: `count >= app_config.seller_classification.min_listings` = **6**, `enabled`, y la fuente no dice `dealer`). `seller_type` nunca se reescribe. `intelligence/seller.py` y `web/lib/seller.ts`: la inferencia gana aun sobre «particular» (Juan, 30/10); el motivo del match dice «posible agencia (publica N autos)» **solo si la búsqueda tiene preferencia de vendedor**.
- **Reposts.** `probable_repost_of` (fingerprint: marca, modelo, año, km redondeado, vendedor, ubicación; misma fuente) y `pipeline/news.py` (`_republished`). No hay dedupe entre fuentes.
- **Imágenes.** `listings.images` (jsonb, lista de URLs). En los fixtures: MercadoLibre 10 (`http2.mlstatic.com`), Rosario Garage 10, V6 5 (`firebasestorage.googleapis.com`), Autocosmos 1 (`*.blob.core.windows.net`), Facebook/Instagram en `scontent*/fbcdn` (URLs firmadas que expiran). No hay ninguna descarga de imágenes en el worker, ni Pillow ni imagehash en `worker/requirements.txt` (Pillow 12.3 está en el entorno de desarrollo, no en el VPS).
- **Enrichment.** `pipeline/enrich.enrich_pass` lee la página de detalle de avisos con match (más los de precio parcial y la banda de referencia), por fuente en paralelo, con `detail_interval_seconds`. El presupuesto LLM usa un ledger con lock advisory (`reserve_description_run`, tabla `description_llm_runs`): es el molde para el tope diario de descargas.
- **Zonas.** `listing_zones` (F-03): `province_id`, `department`, `locality_id`, `precision ∈ locality|province|source_default`.
- **Config `risk`.** `{"checklist_enabled": true, "links": {...}}` (migración `20261122120000`); `webConfig()` la lee; `/admin/config` valida `risk` con zod.
- **Eventos.** `risk_checklist_viewed` y `risk_checklist_copied` existen (Server Action `trackRiskChecklist`); `risk_checklist_copied` está en `admin_decision_metrics.human_events` (última definición `20261128120200`). Falta `duplicate_link_clicked`.
- **RLS.** `listings` es legible por cualquier autenticado: la ficha del otro aviso abre para cualquier usuario.

## Mediciones en la base local

La base local (`127.0.0.1:54322`, `max(version)` = `20261201120000`) tiene **60 avisos de fixtures e2e** (MercadoLibre 58, Autocity 2), ninguno con imágenes. No sirve para medir falsos positivos reales; lo que sí muestra:

- **Datos sin fotos no alcanzan.** Con «mismo modelo y año, km ±3 %, precio ±5 %» hay **113 pares** entre 54 avisos de la *misma* fuente y 0 entre fuentes. Los fixtures repiten adrede autos idénticos (12 Corolla 2017, 90.000 km, $20M, mitad agencia y mitad particular): así se ve un stock de agencia o una versión popular con km y precio redondos. La regla de datos sola, sin más guardas, marcaría todos esos grupos. De ahí las guardas de la decisión 4 y que el nivel sin fotos arranque en **sombra**.
- **`private_many_listings`.** 2 avisos activos (Ford Ka, `seller_type = private`, `seller_listing_count = 7`, `dealer_inferred = true`) cumplirían la regla: coincide exactamente con los que F-02 ya marca y dice particular.
- **pHash (prueba en el scratchpad, no en el repo).** Implementación solo-Pillow (decisión 5) sobre 6 JPEG de 600–720 px de ancho (capturas, no fotos de autos): 9,5 ms por hash. Distancia contra la misma imagen re-escalada al 50 %: 0–2; re-comprimida a calidad 40: 0–2; +20 % de brillo: 2; con una franja blanca en el 10 % inferior (marca de agua): 2–12; **recortada 5 % por lado: 16–20** (no se detecta). Entre imágenes distintas: mínimo 10, mediana 24. Con `phash_max_distance = 6` se detectan re-subidas y re-compresiones (el caso típico de fotos copiadas entre portales), no recortes. La separación real entre fotos de autos distintos del mismo modelo desde el mismo ángulo **no está medida**: queda para la etapa en sombra con datos de producción (decisión 9).

## Decisiones de diseño

### 1. `private_many_listings` sin umbral nuevo y sin repetir «posible agencia»

- **Regla:** `seller_type == 'private'` **y** `dealer_inferred` **y** `seller_listing_count` no nulo. Es decir, exactamente los avisos que F-02 infiere como agencia aunque la fuente diga «particular». Mismo umbral (`seller_classification.min_listings` = 6, 30 días), mismo interruptor (`seller_classification.enabled = false` apaga las dos cosas) y la misma frescura (F-02 ya re-puntúa cuando cambia N de un aviso inferido). No hay razón para un umbral distinto: con dos umbrales un vendedor podría ser «posible agencia» sin la señal o al revés.
- **Fuera:** `seller_type` nulo con 6+ avisos (no «se presenta como particular»; el motivo ya dice «posible agencia» cuando corresponde) y `dealer` (es agencia declarada).
- **Convivencia de mensajes.** El motivo del match (sección «Por qué coincide», solo con preferencia de vendedor) dice *qué es* («posible agencia (publica 7 autos)»); la señal (sección «Conviene verificar», siempre) dice *qué hacer*. El texto de la señal no usa «agencia» ni «revendedor»: no afirma lo que F-02 solo infiere.
- **Copy** (el del backlog): «El vendedor tiene {n} publicaciones activas: conviene preguntar si es titular.» Severidad `info`.
- **Pregunta al vendedor** (propuesta, `seller_questions`/`contact_questions`): «¿El auto está a tu nombre? Si no, ¿quién es el titular y puede estar en la firma?» Cambia el texto de preguntas de esos matches (no el score). Ver pregunta 2.

### 2. Almacenamiento de duplicados: tabla `listing_duplicates`

Las tres señales de duplicado son relaciones entre dos avisos. Se guardan en una tabla nueva, escrita solo por el worker, en ambos sentidos:

```
listing_duplicates(
  listing_id   bigint → listings on delete cascade,
  other_id     bigint → listings on delete cascade,
  kind         text check (kind in ('duplicate_photos', 'cross_source_photos', 'cross_source_data')),
  shown        boolean not null,      -- false = modo sombra: se guarda y se mide, no se muestra
  photo_distance smallint,            -- null para cross_source_data
  evidence     jsonb not null,        -- {km_pct, price_pct, dist_km, zone, matched: [[i, j, d]], rule_v}
  detected_at  timestamptz not null default now(),
  primary key (listing_id, other_id), check (listing_id <> other_id))
```

RLS habilitada sin políticas (solo `service_role`), como `seller_classification_runs`. Un par vive mientras los dos avisos estén activos; el job borra los pares con un aviso `gone` y los que ya no cumplen. `rows_for_scoring` suma un `jsonb_agg` lateral de los pares `shown` con el otro aviso activo: `risk_duplicates = [{other_id, kind, source, source_name, url, distance}]`, a lo sumo 3 por aviso (el de menor distancia / menor diferencia de precio primero). **Por qué no `attributes._duplicates`:** el merge de ingest conserva claves viejas, un par necesita escribirse en los dos avisos a la vez y la etapa en sombra necesita poder contarse por SQL.

Las reglas siguen puras: `red_flags()` lee `listing["risk_duplicates"]` y `listing["seller_type"/"dealer_inferred"/"seller_listing_count"]`; la detección (I/O) vive en `worker/pipeline/risk_duplicates.py` + `db/repos/duplicates.py`.

### 3. Una flag por aviso y por tipo, con link

- `RedFlag` suma un campo opcional `link: {listing_id, url, source_name} | None` que `to_json` omite cuando es `None`. La web de `main` ignora el campo extra (tolera matches nuevos), y la web nueva tolera matches viejos sin `link`.
- Si un aviso tiene varios pares, una sola flag por `id`, con el link al mejor par y, si hay más, «(y {k} más)» en el texto.
- **Precedencia por par:** fotos que coinciden **y** datos que coinciden en otra fuente ⇒ `cross_source_duplicate` (mismas fotos); fotos que coinciden con datos distintos, o en la misma fuente pero otra zona ⇒ `duplicate_photos`; datos sin fotos ⇒ `cross_source_duplicate` (datos). Un mismo par nunca genera las dos señales.

### 4. `cross_source_duplicate` en dos niveles

Común a los dos niveles: ambos activos, **fuentes distintas**, misma marca y modelo normalizados (`lower`), mismo año, km de los dos no nulos y `|Δkm| ≤ 3 %` del mayor, `price_usd` de los dos no nulo y `|Δprecio| ≤ 5 %` del mayor, ninguno con `price_partial`, y `probable_repost_of` no los une. No modifica el score; severidad `info`.

- **Nivel «mismas fotos»** (`cross_source_photos`): además al menos un hash de las primeras `photo_hash_count` fotos de cada uno a distancia `≤ phash_max_distance` (todas contra todas: los portales reordenan), sin contar hashes «comunes» (decisión 6). No exige ubicación. Copy: «Parece el mismo auto publicado también en {source} (mismas fotos): conviene comparar las dos publicaciones.»
- **Nivel «datos»** (`cross_source_data`), guardas conservadoras, todas obligatorias:
  1. km de los dos `≥ 10.000` (fuera 0 km y casi nuevos, que son stock repetido).
  2. Versión (`trim`), caja y combustible: si los dos lo informan, iguales.
  3. Ubicación: los dos con `listing_zones.precision = 'locality'`, misma provincia y (mismo departamento o `≤ 50 km` entre coordenadas). Sin zona fina, no hay señal.
  4. Ningún vendedor es agencia efectiva (`effective_seller = 'dealer'`): una agencia multipublica a propósito y su stock repite configuraciones; la señal aporta poco y tiene más falsos positivos.
  5. **Unicidad mutua:** A tiene un solo candidato en la fuente de B y B uno solo en la de A. Dos o más candidatos = configuración común = sin señal (es lo que muestran los 113 pares locales).
  Copy: «Parece el mismo auto publicado también en {source} (mismo modelo, año y kilometraje, precio parecido): conviene comparar las dos publicaciones.»
  **Arranca en sombra** (`risk.cross_source.data_mode = "shadow"`): los pares se guardan con `shown = false` y el informe del tool permite revisar una muestra antes de prenderlo. No pude medir su precisión con datos reales (ver Mediciones).

### 5. pHash: solo Pillow, import perezoso, todo apagado

- **Librería.** `imagehash` arrastra `numpy`, `scipy` y `PyWavelets` (verificado en la metadata de ImageHash 4.3.2): decenas de MB en el VPS para 64 bits por foto. Propuesta: **solo Pillow** (`Pillow==12.3.0` en `worker/requirements.txt`) y un pHash propio de ~30 líneas en `worker/intelligence/photo_hash.py`: escala de grises, 32×32 LANCZOS, DCT-II 2D de los 8×8 de baja frecuencia con matriz de cosenos precalculada, umbral en la mediana, 64 bits en hex. Es el mismo algoritmo que `imagehash.phash` (el factor de escala de la DCT no cambia la comparación con la mediana); la compatibilidad se fija con un test de vectores: hashes esperados (calculados una vez con `imagehash` en dev y guardados en fixtures) para imágenes generadas por el propio test; corre siempre, sin depender de que `imagehash` esté instalado.
- **Import perezoso.** `photo_hash.py` importa `PIL` dentro de la función; si falla, el pass registra una vez «Pillow no instalado» en `pipeline_errors` y no hace nada. El worker arranca y funciona igual sin la librería.
- **Cuándo.** Un paso `photo_hash_pass()` al final de `enrich_pass` (después del drain, antes del rescore de lo cambiado), con su propio presupuesto: no frena las páginas de detalle ni usa el presupuesto LLM.
- **Cola.** Avisos activos con match vivo o de precio parcial **y** sus candidatos de datos en otra fuente (misma marca, modelo y año, km y precio en tolerancia): sin el otro lado hasheado no hay par. Más nuevos primero; nunca fuentes en `risk.photo_hash.skip_sources`.
- **Descarga.** `httpx` con el proxy del worker, `timeout_seconds` (10), tope `max_bytes` (2 MB, por `Content-Length` y leyendo en streaming), solo `image/*`, `Image.MAX_IMAGE_PIXELS` acotado y `draft()` para JPEG, una imagen por host cada `per_host_interval_seconds` (1). Sin cookies ni login: solo la URL pública ya guardada.
- **Tope diario.** Ledger `photo_hash_runs(id, listing_id → set null, started_at, finished_at, images_requested, images_hashed, error)` con el mismo patrón que `reserve_description_run`: lock advisory, ventana móvil de 24 h, la reserva cuenta aunque falle o el proceso muera. Tope `risk.photo_hash.daily_image_cap`.
- **Sin reintentos infinitos.** `attributes._photo_hashes = {"v": 1, "urls": [...], "hashes": ["hex"|null, ...], "at": iso, "attempts": n, "error": str|null}`. Se recalcula solo si cambian las primeras N URLs (entonces `attempts` vuelve a 0); con `attempts >= max_attempts` (2) no se intenta más esas URLs. Escribir `attributes` no dispara `listing_updated` (no es `KEY_ATTR`).
- **Después de hashear** un aviso, la detección corre para él (decisión 7) y se re-puntúan los avisos cuyos pares cambiaron.

### 6. `duplicate_photos`

- **Regla:** mismo modelo (marca y modelo normalizados; el año no, una foto robada puede venir con otro año), al menos un hash compartido a `≤ phash_max_distance`, y (fuente distinta **o** misma fuente con zona distinta: `listing_zones.department` distinto o `> 50 km`, con precisión `locality`), y el par **no** cumple los datos del nivel «mismas fotos» de la decisión 4. Misma fuente y misma zona con las mismas fotos es una re-publicación: ya la cubre `repost`.
- **Hashes comunes fuera:** un hash que aparece (a `≤ phash_max_distance`) en avisos de 3 o más vendedores distintos (`risk.photo_hash.common_min_sellers`) es una foto de catálogo, un logo o un placeholder; no cuenta. También los hashes casi constantes (imagen lisa: `0x0…`/`0xf…`, ≤ 4 bits en 1 o ≥ 60).
- Se marca en **los dos** avisos. Severidad `warning`. Copy: «Las fotos de esta publicación aparecen también en otra publicación ({source}) con otros datos: conviene pedir fotos actuales y ver el auto antes de señar.» Abre expandido el bloque «Antes de señar» (se suma a `emphasize()` junto a `much_cheaper` y `partial_price_suspect`).

### 7. Detección: job completo, incremental y backfill

- `pipeline/risk_duplicates.py`:
  - `detect_all(trigger, dry_run, report)`: por (marca, modelo) con avisos activos en 2+ fuentes o con hashes, compara en Python (grupos chicos), reescribe los pares de ese grupo en una transacción por lote y re-puntúa los avisos cuyo conjunto de pares `shown` cambió. Corre en el arranque y en el slot ancla nocturno, después de `classify_sellers` y antes de `rescore_recent` (`pipeline/rescore.py`).
  - `detect_for(listing_ids)`: lo mismo acotado a los grupos de esos avisos; se llama después de `classify_groups` en `ingest.py` y después de `photo_hash_pass`. Nunca levanta: un error se registra y el job completo lo arregla.
- **Backfill:** `python -m tools.risk_duplicates [--dry-run] [--report] [--group "Ford/Fiesta"]`. Idempotente (reescribe por grupo el estado deseado; correrlo dos veces no cambia nada), `--dry-run` no escribe ni re-puntúa e imprime cuántos pares de cada `kind` crearía/borraría, y `--report` lista hasta 20 pares por `kind` con los dos links, Δkm, Δprecio, distancia y zona: es la herramienta para revisar la sombra.
- El job respeta `risk.signals`: un `kind` en `"off"` no se calcula (y se borran sus pares), en `"shadow"` se guarda con `shown = false`, en `"on"` con `shown = true`.

### 8. Orden de prioridad configurable (`app_config.red_flags.order`)

- `red_flags.order`: lista de ids. El worker ordena la lista al armarla (orden configurado; ids que no figuren, al final en orden de emisión) y la guarda ya ordenada. `flag_texts` ordena por la posición en `order` (leída de la config, así también reordena matches viejos) y toma las 2 primeras. La ficha sigue agrupando por severidad (`warning` arriba, orden estable): con el default las tres `warning` ya son las primeras de `order`, así que ficha y email coinciden; si Juan pone una `info` por encima de una `warning`, el email la respeta y la ficha mantiene el agrupamiento visual.
- **Default** (no cambia ningún email existente: reproduce el orden de hoy y solo intercala las nuevas):
  `duplicate_photos, much_cheaper, partial_price_suspect, private_many_listings, cross_source_duplicate, no_owners, service_unavailable, no_service, timing_pending, no_timing_belt, short_description, damage_mentioned, commercial_use, vtv_pending, low_km_for_age, repost, price_mismatch, year_mismatch, km_mismatch`.
  Con esto un email con `much_cheaper` + `private_many_listings` muestra las dos; uno con `duplicate_photos` + `much_cheaper` muestra esas dos.
- `validateConfigChange("red_flags")` (ya valida la coherencia de umbrales) suma: `order` es una lista de ids conocidos, sin repetidos. Un id desconocido se rechaza en `/admin/config`; el worker igual lo ignora.

### 9. Config nueva en `app_config.risk` (se agrega solo lo que falte)

```json
{
  "photo_hash_count": 3,
  "phash_max_distance": 6,
  "photo_hash": {"enabled": false, "daily_image_cap": 600, "max_attempts": 2, "max_bytes": 2000000,
                 "timeout_seconds": 10, "per_host_interval_seconds": 1, "common_min_sellers": 3,
                 "skip_sources": ["facebook", "instagram"]},
  "cross_source": {"km_tol_pct": 3, "price_tol_pct": 5, "data_min_km": 10000, "data_max_dist_km": 50},
  "signals": {"private_many_listings": "on", "cross_source_photos": "on",
              "cross_source_data": "shadow", "duplicate_photos": "on"}
}
```

- Con `photo_hash.enabled = false` no se descarga nada y no existen pares de fotos: las señales de fotos quedan en `"on"` pero no tienen insumo. Prender el hash es la aprobación; si Juan prefiere una semana de sombra también para las de fotos, se ponen en `"shadow"` (pregunta 4).
- `intelligence/config.risk(raw)` normaliza clave por clave con cotas (como `seller_classification`): `photo_hash_count` 1–5, `phash_max_distance` 0–16, `daily_image_cap` 0–5000, tolerancias 0–20 %, `signals.*` ∈ `on|shadow|off`. Valor ausente o inválido = default. `validateConfigChange("risk")` suma las mismas cotas con zod y sigue validando `links`.

### 10. Ficha y email

- **Ficha.** Mismas filas de «Conviene verificar» (ícono y estilo por severidad). Si la flag trae `link`, al final del texto un link «Ver la otra publicación»: a `/app/listings/{listing_id}` si el aviso sigue en la base (la página consulta en una sola query `select id from listings where id in (...)` los ids de los links), si no a `url` externa con `target="_blank" rel="noopener noreferrer"`. Componente cliente `web/components/app/duplicate-link.tsx` que llama a la Server Action `trackDuplicateLink` sin bloquear la navegación.
- **Email.** Sin cambios de plantilla: hasta 2 flags por el orden de la decisión 8, sin link (el email ya lleva a la ficha). Snapshots nuevos.

### 11. Eventos

- `duplicate_link_clicked` con `{listing_id, other_listing_id, kind: "duplicate_photos" | "cross_source_photos" | "cross_source_data", target: "internal" | "external"}`, vía Server Action con zod (ids enteros positivos, `kind` y `target` en lista cerrada), solo a la tabla `events`.
- Se suma a `admin_decision_metrics.human_events` (acción explícita, como `risk_checklist_copied`) en una migración aparte, `create or replace` completo desde `20261128120200` con solo esa línea cambiada (pregunta 6).
- No faltan otros eventos del backlog para PAR-02 (`risk_checklist_viewed`/`_copied` existen).

### 12. Rollback

`risk.signals.<kind> = "off"` saca una señal en el próximo rescore (el job borra sus pares y re-puntúa); `photo_hash.enabled = false` corta descargas; `seller_classification.enabled = false` apaga `private_many_listings` junto con la inferencia; borrar `red_flags.order` vuelve al orden de emisión. Sin deploy en ningún caso.

## Datos y migraciones

Versiones `>= 20261203120000` (producción en `20261201120000`; **releer `max(version)` de producción antes de nombrar**). Aplicables desde base vacía (`lock table` dentro de `do $$`, `set local lock_timeout`).

1. `20261203120000_par02_duplicates.sql`: tablas `listing_duplicates` (índice por `other_id`) y `photo_hash_runs` (índice por `started_at`), RLS sin políticas y `revoke` a `anon`/`authenticated`; `app_config.risk = value || {claves nuevas}` solo para las que falten (con `jsonb_typeof(value) = 'object'`); `app_config.red_flags.order` si falta. Sin cambios en `listings`. La web de `main` no lee nada de esto: tolera la base con o sin la migración. El worker nuevo **sí** necesita la migración (lee `listing_duplicates` en `rows_for_scoring`): se despliega después; para no atar el orden, `rows_for_scoring` consulta `to_regclass('public.listing_duplicates')` una vez por proceso y sin la tabla devuelve `risk_duplicates = []`.
2. `20261203120100_par02_decision_metrics_duplicate.sql`: `admin_decision_metrics` con `duplicate_link_clicked` (sola, con su pgTAP).

También: `supabase/seed.sql` (`risk` y `red_flags` completos), `DEFAULT_RED_FLAGS`/`DEFAULT_RISK` en `intelligence/config.py`, `HINTS` de `/admin/config`, `web/lib/types.ts` (`RedFlag.link?`), `web/types/database.ts` a mano (las dos tablas, aunque la web no las use, para que el tipo refleje la base), `docs/TECHNICAL_PLAN.md` (eventos).

**Sin bump de `SCORING_VERSION`:** las flags no entran al score. Los matches existentes reciben las flags nuevas cuando el job las detecta (re-puntúa en el momento) o con el rescore de 14 días.

## Validación

- **Worker (pytest):**
  - `red_flags`: vendedor con 6 avisos y `seller_type = private` ⇒ `private_many_listings` con N; con `seller_type = null` o `dealer`, o `dealer_inferred = false` ⇒ no; `seller_classification.enabled = false` ⇒ no. Mismo `score`, `level` y demás flags antes y después (comparando `assess`), y el snapshot de la clasificación de F-02 no cambia.
  - Duplicados (pura, con filas armadas): dos avisos en dos fuentes con el mismo hash y datos en tolerancia ⇒ `cross_source_duplicate` (fotos) en los dos y no `duplicate_photos`; mismo hash con precio 20 % distinto ⇒ `duplicate_photos` en los dos; mismo hash en la misma fuente y zona ⇒ nada; mismo hash en 3 vendedores ⇒ nada (común); datos sin hash: un par único con zona fina ⇒ par `cross_source_data` en sombra (`shown = false`, sin flag) y con `data_mode = "on"` ⇒ flag; un tercer candidato ⇒ nada; km < 10.000, agencia, sin zona fina, km +4 % o precio +6 % ⇒ nada.
  - `photo_hash.py`: vectores fijos (imagen generada en el test, re-escalada y re-comprimida ⇒ distancia ≤ 2; dos imágenes distintas ⇒ > 6); sin Pillow (import simulado que falla) el pass no levanta y registra el error una vez; tope diario y `max_attempts` respetados con un servidor HTTP falso (`httpx.MockTransport`); respuesta > `max_bytes`, `text/html` o timeout ⇒ hash nulo y `attempts + 1`; fuentes de `skip_sources` nunca se descargan; `enabled = false` ⇒ cero requests.
  - Postgres (`TEST_DATABASE_URL`, `python -m tools.test_db`): `detect_all` idempotente (dos corridas, mismo estado), `--dry-run` no escribe, un aviso `gone` borra sus pares, re-puntúa solo lo que cambió.
  - Orden: tabla de combinaciones ⇒ las 2 del email; sin `order` en la config ⇒ igual que hoy (test de regresión contra el orden actual con todas las flags existentes).
  - Lint de copy: los textos nuevos están en `copy.RED_FLAG` (los recorre `test_intelligence_copy.py`), más una lista propia de vedadas para las nuevas: «robad», «estafa», «fraude», «verificado por Ese Auto», «certificad», «garantiz», «agencia», «revendedor».
  - Snapshots de email (`worker/tests/snapshots/notifications/`): `private_many_listings` + `much_cheaper`; `duplicate_photos` + `much_cheaper` + una info (corta en 2).
- **Web (vitest):** snapshot de la sección «Conviene verificar» con las tres flags nuevas (link interno, link externo cuando el otro aviso no está, flag vieja sin `link`); la Server Action rechaza props inválidas y llama a `track` con lo esperado; lint de copy del componente nuevo; `validateConfigChange` de `risk` y `red_flags.order`.
- **Playwright (desktop y 375 px):** la ficha con un `cross_source_duplicate` muestra el link, el click registra `duplicate_link_clicked` y abre la ficha del otro aviso; sin scroll horizontal.
- **pgTAP:** `supabase/tests/par02_duplicates_test.sql`: tablas, PK/check/FK con cascade, RLS habilitada, `anon`/`authenticated` sin acceso, claves nuevas de `risk` con sus defaults sin pisar `checklist_enabled` ni `links`, `red_flags.order` agregado sin tocar umbrales; `admin_decision_metrics_test.sql` con el evento nuevo.

## Riesgos

- **Falsos positivos de datos sin fotos:** sin datos reales no se pudo medir; mitigado por guardas y sombra.
- **Fotos de autos parecidos:** el pHash separó imágenes distintas a ≥ 10 bits en la muestra, pero no eran fotos de autos; fotos de estudio del mismo modelo (agencias, Kavak) pueden acercarse. Mitigado por «hash común» y la precedencia; medir en producción antes de bajar/subir `phash_max_distance`.
- **Recortes y marcas de agua:** un recorte de 5 % ya da 16–20 bits; quien recorta las fotos no se detecta. La señal es «cuando coincide, avisa»; nunca se presenta como detección completa.
- **Facebook/Instagram:** URLs firmadas que expiran y términos de uso; por eso quedan en `skip_sources` hasta que Juan decida. Sin ellas se pierde justamente la fuente donde más se repiten fotos.
- **Carga:** 600 imágenes/día × ~200 KB ≈ 120 MB/día de tráfico entrante y ~6 s de CPU; despreciable, pero son requests a CDNs de terceros con el IP del VPS.
- **Texto guardado:** los matches que no se re-puntúan (avisos no vistos en 14 días) quedan sin las flags nuevas; aceptable (son avisos viejos).

## Preguntas para Juan

1. **`private_many_listings`:** ¿aprobás que sea exactamente «dice particular + posible agencia de F-02» (mismo umbral 6 en 30 días, mismo interruptor) y el copy del backlog «El vendedor tiene N publicaciones activas: conviene preguntar si es titular»? ¿Y que no aparezca cuando la fuente no informa el tipo de vendedor? (propuesto: sí y sí).
2. ¿Sumamos la pregunta al vendedor «¿El auto está a tu nombre? Si no, ¿quién es el titular y puede estar en la firma?» cuando aparece esa señal? (propuesto: sí).
3. **Instalar Pillow en el VPS** (`Pillow==12.3.0`, ~5 MB) en lugar de `imagehash` (+ numpy, scipy, PyWavelets). ¿OK? (propuesto: solo Pillow).
4. **Prender el hash:** ¿con las señales de fotos directamente visibles o primero una semana en sombra? (propuesto: una semana en sombra, revisar `tools.risk_duplicates --report` y después `"on"`).
5. **Tolerancias y topes:** `photo_hash_count` 3, `phash_max_distance` 6, `daily_image_cap` 600 imágenes/día, `max_attempts` 2, `max_bytes` 2 MB, 1 imagen por segundo por host, foto «común» desde 3 vendedores. ¿OK?
6. **Política de imágenes de Facebook e Instagram:** ¿se descargan sus fotos (URLs firmadas que expiran, términos de uso) o quedan excluidas? (propuesto: excluidas en `skip_sources` hasta que lo decidas).
7. **Duplicado sin fotos:** ¿aprobás las guardas (km ≥ 10.000, versión/caja/combustible iguales si están, misma localidad o ≤ 50 km, sin agencias, candidato único) y arrancar en sombra hasta revisar una muestra de producción? (propuesto: sí).
8. **Orden de prioridad** en el email: `duplicate_photos`, `much_cheaper`, `partial_price_suspect`, `private_many_listings`, `cross_source_duplicate` y después las de hoy en su orden actual. ¿OK? ¿Querés que `private_many_listings` sea `warning` (texto naranja) en vez de `info`? (propuesto: `info`, alto en el orden).
9. **Copys** de `duplicate_photos` («Las fotos de esta publicación aparecen también en otra publicación ({source}) con otros datos: conviene pedir fotos actuales y ver el auto antes de señar.») y de los dos niveles de `cross_source_duplicate` (decisión 4), y el link «Ver la otra publicación».
10. **Métricas:** ¿`duplicate_link_clicked` cuenta como actividad en `admin_decision_metrics` (migración propia)? (propuesto: sí).
11. **Producción:** OK para aplicar las dos migraciones (transacción + versión exacta + `max(version)`) y desplegar el worker con `wait_idle`, cuando esté el plan.

## Siguiente paso

Con tu aprobación escribo el plan en `docs/superpowers/plans/2026-11-02-par02-resto.md` (tareas con tests primero) en la rama `claude/par02-riesgo`. Orden propuesto de entrega: (a) `private_many_listings` + orden configurable (sin migración de esquema más que la config); (b) tabla, job, backfill y `cross_source_duplicate` de datos en sombra; (c) pHash apagado + `duplicate_photos` + nivel «mismas fotos»; (d) web (link + evento) y métricas.
