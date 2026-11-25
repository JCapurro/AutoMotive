# Plan: que el usuario no vea autos que ya terminaron

Fecha: 2026-11-25. Estado: **solo diseño**. No se tocó código, datos ni `app_config`. Juan elige la opción.

---

## 1. Cómo funciona hoy (verificado en el código)

**Cuándo un auto pasa a `gone`.** Solo cuando una página de detalle prueba que terminó:
- `refresh_listing` en `worker/pipeline/enrich.py:121` baja la página.
- `ingest_detail` llama a `mark_gone` (`worker/db/repos/listings.py:240`), que emite `listing_gone` una sola vez.
- Salir de los 96 primeros resultados de la búsqueda no cuenta como prueba.
- Si la descarga o el parseo fallan, el error queda en `pipeline_errors`, se marca `detail_checked_at` y se reintenta después.

**Quién re-chequea.** La lista de seguimiento, `worker/pipeline/watchlist.py`, se despierta cada `WATCHLIST_TICK_SECONDS` = 3600 s (`worker/config.py:76`). Tiene dos colas:
- **Guardados o seguidos** (`watchlist_queue`, `listings.py:478`): se chequean cada 20 h.
- **Con match** (`matched_recheck_queue`, `listings.py:496`, config `app_config.watchlist_matched`):
  - entran los autos con match `<> 'low'` en una búsqueda viva;
  - que el rastreo no ve hace 6 h (`unseen_hours`);
  - que no se chequearon en 12 h (`recheck_hours`);
  - con `first_seen_at` de hasta 60 días;
  - **como máximo 20 por fuente y por pasada (`per_source`)**, empezando por el `detail_checked_at` más viejo.
- En producción no hay fila `watchlist_matched`, así que rigen esos valores por defecto: unas **480 páginas por fuente por día como máximo**.

**Ritmo por fuente.** `drain` (`enrich.py:200`) procesa cada fuente en serie, respetando `sources.detail_interval_seconds`. En producción ese intervalo es de 8 s en ML, 30 s en FB, 6 s en DeRuedas y 5 s en el resto.

**Qué hace el envío.**
- `public.prepare_notification_delivery` (vigente en `20261118120000_free_results_cap_50.sql:128`) descarta (`skipped`, `listing_unavailable`) un `new_match`, `opportunity` o `price_drop` cuyo auto no está `active`.
- En los resúmenes (digest) filtra los ítems que no están `active`.
- Solo mira la columna `status`: no hace ningún chequeo en vivo.

**Qué muestra el panel `/app`.**
- `search_results`, `dashboard_summary` y `recent_opportunities` filtran `listing_status='active'`.
- Guardados y descartados muestran «Ya no está disponible» si el auto está `gone`.
- Un auto muerto que todavía no se marcó `gone` se ve como vigente.

**Canales.** El enum es `telegram | email | web | push`. **WhatsApp no es un canal de alertas en el worker**. En los últimos 14 días todo lo enviado fue por email.

**Trampa de medición.** Cuando un chequeo encuentra el auto vivo, `update_listing` (`listings.py:87-90`) renueva `last_seen_at`. Consecuencias:
- No existe `gone_at`. La última señal de vida de un auto `gone` es `last_seen_at` y la detección es `detail_checked_at`.
- No se puede medir directamente qué fracción de los «no vistos hace X» está muerta, porque los vivos se renuevan y salen de la consulta.

## 2. Mediciones en producción (2026-11-25, solo lectura)

### 2.1 Notificaciones: casi limpias al enviarse

Ventana: últimos 14 días, 1.315 alertas `new_match`, `opportunity` y `price_drop` enviadas.

| Tipo | Enviadas | Hoy `gone` | Clics | Clic en auto ya muerto |
|---|---|---|---|---|
| new_match | 722 | 18 (2,5 %) | 56 | 0 |
| opportunity | 396 | 14 (3,5 %) | 20 | 1 |
| price_drop | 197 | 10 (5,1 %) | 12 | 0 |
| Ítems dentro de resúmenes | 1.145 | 7 (0,6 %) | — | — |

- **Solo 4 de 1.315 (0,3 %) pudieron estar muertas al enviarse**: son autos hoy `gone` que nadie vio vivos después del envío. Para las otras 38, hubo una señal de vida posterior al mail.
- `new_match` y `opportunity` salen con mediana de **segundos** desde que el auto apareció. Ningún envío fue de un auto no visto hace más de 24 h.
- Entre el mail y la detección del fin pasan, en mediana, 144 h en ML, 53 h en FB y 77 h en RosarioGarage. El auto muere días después del aviso.
- La excepción es **`price_drop`**: 144 de 197 son autos con más de 72 h en la base, y 10 de esos 144 (7 %) ya terminaron.
- Resúmenes: mediana de 8 a 10 h entre el ítem y el envío. Solo 1 de 1.145 salió con el auto ya `gone`, así que el filtro actual funciona con lo que sabe.

### 2.2 El panel está lleno de autos dudosos

Universo: búsquedas activas (`search_profiles.enabled`), matches `<> 'low'`, autos `active`.

| | Tarjetas | No vistas hace más de 48 h |
|---|---|---|
| Todas | 16.128 | **5.124 (32 %)**, en 56 de 82 usuarios |
| Solo `high` | 377 | 45 (12 %) |

Autos distintos no vistos hace más de 48 h dentro de búsquedas activas:

| Fuente | Autos |
|---|---|
| mercadolibre | 3.274 |
| facebook | 994 |
| carone | 78 |
| resto | 0 |

Contando todas las búsquedas, incluidas las apagadas, la cola elegible para `watchlist_matched` es mucho mayor: ML 10.972, FB 3.441, DeRuedas 1.845 y RosarioGarage 909. Con 20 por pasada, nunca se vacía. Además, la orden «el `detail_checked_at` más viejo primero» gasta el cupo en autos de búsquedas que ya nadie mira.

### 2.3 Demora para detectar el fin

Se detectan entre 250 y 820 fines por día. En las últimas 24 h fueron 365 de ML, 70 de FB, 28 de Kavak, 24 de RosarioGarage y 12 de CarOne.

| Fuente | Mediana desde la última vez visto | p90 |
|---|---|---|
| mercadolibre | **358 h (15 días)** | 653 h |
| facebook | 48 h | 515 h |
| deruedas | 147 h | 404 h |
| kavak | 102 h | 431 h |
| rosariogarage | 108 h | 432 h |

Señal de cuántos dudosos están muertos: de los re-chequeados esta semana que llevaban más de 48 h sin verse, 2.347 de ML quedaron `gone` y solo 10 siguen `active` con esa marca. FB, Kavak y DeRuedas dan cerca del 100 %. Está sesgado por la trampa de §1, así que no prueba «99 % muertos». Sí confirma que **un auto con match y más de 48 h sin verse, al chequearlo, sale `gone` muy seguido**.

### 2.4 Conclusiones

1. El mail **casi nunca** lleva un auto muerto al momento de enviarse (0,3 %). Lo que falla es lo que pasa después: el panel, el resumen y el tiempo hasta el clic.
2. El problema grande es **el panel**: un tercio de las tarjetas son autos sin señal de vida hace más de 48 h, y en ML el fin tarda dos semanas en detectarse.
3. El límite es el **ritmo y el orden** del re-chequeo (20 por pasada, sin prioridad), no la señal de fin, que ya existe y funciona en todas las fuentes.

## 3. Señales de «terminó» por fuente y costo del chequeo

Ninguna fuente tiene hoy una vía liviana implementada: todas bajan la página completa. Tampoco hay proxies. El breaker (`worker/pipeline/breaker.py`) pausa la fuente 30 min ante un `CollectorBlocked`, y su estado vive en la memoria del proceso.

| Fuente | Cómo se lee | Señal de fin | Capacidad por día (intervalo actual) | Riesgo de bloqueo |
|---|---|---|---|---|
| MercadoLibre | httpx, 8 s | 404; «publicación pausada/finalizada»; JSON-LD `availability` distinto de InStock | ~10.800 a tiempo completo | Medio: 403/429 o challenge pausan la fuente; comparte reputación con el rastreo |
| Facebook | Playwright aislado, sesión `fb_state.json`, 30 s | redirect o `unavailable_product`; «ya no está disponible»; título «Vendido ·»; en la búsqueda, `card_status` sold | ~2.880 en teoría, pero cada página gasta sesión | **Alto**: la sesión es frágil y renovarla es manual |
| DeRuedas | httpx sin redirects, 6 s (robots) | 302 a `/` | ~14.000 | Bajo |
| Kavak | httpx, 5 s | 404; sin JSON-LD Car; id distinto | ~17.000 | Bajo |
| Autocosmos | httpx, 5 s | 404/410; `.m-vendido` | ~17.000 | Bajo (401/403/429 pausan la fuente) |
| Regionales (CarOne, RosarioGarage, V6, etc.) | httpx, 5 s | 404/410; vendido/reservado; 302 al inicio | ~17.000 | Bajo |

**Vía liviana posible para ML: la API pública `items`** (multiget de hasta 20 ids por request, con campo `status` active/paused/closed).
- No está implementada.
- Hay que verificar si hoy pide token. Si lo pide, crear una app de desarrollador de ML, que es gratis pero es una cuenta nueva: decisión de Juan.
- Bajaría el costo de ML unas 20 veces y no compite con el rastreo.
- Es un cambio de fuente, así que necesita OK.

**Carga en el VPS.** El chequeo por httpx es despreciable. El de FB abre Chromium en un subproceso por página, así que conviene mantenerlo en decenas por hora.

## 4. Métricas comunes a todas las opciones

Se miden con una consulta de solo lectura, antes y después. Se pueden sumar al panel de `/admin`.

- **M1. Envíos con auto muerto:** porcentaje de alertas enviadas (`new_match`, `opportunity`, `price_drop` e ítems de resumen) cuyo auto hoy está `gone` y no tuvo ninguna señal de vida después del envío (`last_seen_at < sent_at`). Hoy: **0,3 %** (4/1.315). Objetivo: menos de 0,1 %.
- **M2. Clic en auto muerto:** clic en una alerta o en el panel cuyo auto se detecta `gone` hasta 24 h después del clic sin haberse visto vivo después. Hoy: 1 de 88 clics. Objetivo: 0.
- **M3. Tarjetas dudosas en el panel:** porcentaje de tarjetas de búsquedas activas (`<> 'low'`) sin señal de vida hace más de 48 h. Hoy: **32 %** (5.124/16.128). Objetivo: menos de 5 %. Requiere una columna de «última vez visto vivo» (ver Opción D, que la agrega).
- **M4. Demora de detección:** mediana y p90 de `detail_checked_at - last_seen_at` de los `gone` de la semana, por fuente. Hoy ML 358 h / 653 h. Objetivo: menos de 48 h / 96 h.
- **M5. Costo:** páginas de detalle por fuente y por día (`raw_pages` por `stage`), pausas del breaker por día y renovaciones de la sesión de FB. No deben empeorar.

---

## 5. Opciones

### Opción A: chequeo en vivo justo antes de enviar

**Qué hace.** En `notifications/dispatch.py`, antes de `prepare_delivery`, re-chequea en vivo con `refresh_listing(row, stage="presend")`:
- cada `price_drop`;
- cada ítem de resumen;
- cualquier alerta cuyo auto no tenga señal de vida hace más de `max_age_hours` (por ejemplo 6 h).

Los autos recién vistos, que son la mayoría de `new_match` y `opportunity`, no se chequean. Si el chequeo dice `gone`, la función actual ya los descarta.

- **Señal:** la misma página de detalle.
- **A quién prioriza:** solo lo que está por salir.
- **Cadencia:** al despachar, que corre cada 60 s. Una espera máxima por chequeo de unos 20 s. Si falla o la fuente está pausada, se manda igual (`on_error: send`) para no atrasar alertas.
- **Costo:** muy bajo. Del orden de 15 `price_drop` por día más unos 80 ítems de resumen por día, casi todos ML. En FB, solo `price_drop` viejos: unos pocos por día.
- **Cambios:**
  - un paso nuevo en `dispatch.py`;
  - `app_config.availability_presend = {enabled, max_age_hours: 6, kinds: [...], sources: [...], timeout_s: 20, on_error: "send"}`;
  - sin migración.
- **Qué mueve:** M1, de 0,3 % a unos 0,05 %. **No mueve M3** (el panel) ni M4.
- **Esfuerzo:** chico, 1 o 2 días con tests.
- **Riesgos:** el despacho se vuelve más lento; si una fuente tarda, atrasa el resumen. Mitigación: tiempo máximo por lote.
- **Cómo se revierte:** `enabled: false`.

### Opción B: re-chequeo priorizado por valor (ampliar `watchlist_matched`)

**Qué hace.** Mantiene la cola actual pero cambia el cupo y el orden.

1. **Cupo por fuente** en vez de 20 fijos: `per_source: {mercadolibre: 150, facebook: 15, carone: 40, default: 40}`.
2. **Tick propio de 15 min** para la cola de matches, separado del de los guardados, que sigue en 1 h.
3. **Orden por valor.** Se calcula una prioridad en SQL y se procesa de mayor a menor:
   - solo búsquedas `enabled` (hoy también entran las apagadas);
   - `level` (`high` primero), plan del dueño (Pro y Pase primero) y `opportunity`;
   - si el auto está en un resumen pendiente (`notifications.status='digest'`, sin enviar);
   - horas sin verse: lo mejor es entre 24 y 120 h, porque ahí la probabilidad de muerte ya es alta y el usuario todavía lo ve.
4. **Back-off.** Si el auto se chequea vivo pero sigue sin aparecer en la búsqueda, el próximo chequeo se espacia: 12 h, 24 h, 48 h, hasta un tope de 72 h. Así no se martilla lo que sigue vivo. Usa el conteo de chequeos sin aparición; ver la Opción D para dónde guardarlo.

- **Señal:** la página de detalle, sin cambios.
- **Cadencia y costo:**
  - ML: 150 cada 15 min a 8 s son 20 min de carril por hora, unas 14.400 páginas por día como techo. La cola real de búsquedas vivas es de unos 3.300, que se vacía en menos de un día. Después, el ritmo baja a lo que entra.
  - FB: 15 cada 15 min a 30 s son 7,5 min por hora, unas 1.440 por día como techo. Recomiendo arrancar en `facebook: 5` (unas 480 por día) solo para `level` `high` y `medium` de usuarios que pagan.
  - Resto: cola chica, costo despreciable.
- **Cambios:**
  - `matched_recheck_queue` con prioridad y búsquedas `enabled`;
  - `per_source` como mapa;
  - un tick nuevo en `main.py`;
  - una fila `app_config.watchlist_matched` (hoy no existe);
  - sin migración si el back-off se deriva de `detail_checked_at - last_seen_at`. Con la columna de D queda más limpio.
- **Qué mueve:** M3, de 32 % a menos de 5 % en ML y de los regionales, y M4 de ML, de 358 h a menos de 48 h. M1 casi no cambia, porque ya es bajo. FB mejora menos por el cupo chico.
- **Esfuerzo:** medio, 2 o 3 días.
- **Riesgos:** más carga sobre ML. Si aparecen pausas del breaker, se baja el cupo desde `app_config`, sin deploy.
- **Cómo se revierte:** borrar la fila de `app_config`, que vuelve a 20 por fuente y al orden viejo, o poner `enabled: false`.

### Opción C: barrido de rotación sobre todo el inventario `active`

**Qué hace.** Un trabajo nuevo, `pipeline/sweep.py`, recorre todo el inventario `active`, con o sin match, en un ciclo de N días por fuente. Procesa primero el `detail_checked_at` más viejo y corre a baja velocidad en horas tranquilas.

- **Señal:** la página de detalle. En ML, idealmente la API `items` (ver §3).
- **A quién prioriza:** nadie en particular. Sirve para la calidad del inventario (comparables, valor justo, purga, estadísticas de mercado), no para el usuario.
- **Cadencia y costo:**
  - ML: 45.500 autos. Sin la API, un ciclo de 7 días serían unas 6.500 páginas por día, o 14 h por día de carril a 8 s. **Es caro y arriesgado.** Con la API serían unas 330 requests por día.
  - FB: 13.500 autos con sesión frágil. **No es viable**; FB debería quedar fuera.
  - DeRuedas, RosarioGarage, Kavak, Autocosmos y regionales: unos 32.000 autos en total. Con un ciclo de 7 días, unas 4.600 páginas por día repartidas en fuentes de bajo riesgo. Es viable.
- **Cambios:**
  - un pase nuevo;
  - `app_config.inventory_sweep = {enabled, cycle_days: {...}, sources: [...], hours: [...]}`;
  - sin migración.
- **Qué mueve:** M4 en las fuentes barridas, y la limpieza de `active` (hoy 92.697, con muchos muertos). M3 mejora poco, porque lo que importa al usuario ya lo cubre B.
- **Esfuerzo:** medio, 2 días sin la API de ML y 3 o 4 días con ella.
- **Riesgos:** volumen alto contra fuentes chicas. Hay que respetar robots y el intervalo, y es más superficie para bloqueos.
- **Cómo se revierte:** `enabled: false`.

### Opción D: columna de «última vez probado vivo» (solo interna, sin nada visible)

> **Descartado por Juan (2026-11-25):** la etiqueta «sin confirmar» en el panel baja la calidad
> percibida. El usuario solo ve dos estados: vigente o «Ya no está disponible». Queda de D la parte
> interna, que no se ve.

**Qué hace.** Agrega **`listings.alive_checked_at`**: la última vez que una fuente probó que el auto está vivo, sea por búsqueda o por detalle. Esa columna separa «visto en la búsqueda» de «chequeado vivo» y cierra la trampa de §1. Sirve para tres cosas:
1. ordenar y espaciar los chequeos de la Opción B (back-off);
2. medir M3 y la tasa real de muertos entre los no vistos;
3. en ML, cruzarla con las lecturas completas de 48 h (`last_full_seen_at`): si una búsqueda completa que cubre el auto corrió después de su última aparición y no lo encontró, ese auto sube al frente de la cola de B.

- **Señal:** la ausencia, gratis. Solo decide a quién chequear primero; nunca marca nada ni cambia lo que ve el usuario.
- **Costo:** cero requests.
- **Cambios:** una migración con la columna, su relleno desde `last_seen_at` y un índice; escribirla en `update_listing` e ingest. Sin cambios en la web ni en `match_cards`.
- **Qué mueve:** hace medible M3 y mejora la eficiencia de B. Por sí sola no cambia lo que ve el usuario.
- **Esfuerzo:** chico, 1 día (migración, ingest y test).
- **Cómo se revierte:** se deja de usar; la columna no molesta.

### Opción E: chequeo a pedido cuando el usuario mira (al abrir o hacer clic)

**Qué hace.** Cuando un usuario abre el detalle en `/app` o hace clic en un link firmado de mail, la web inserta una fila en una cola nueva, `availability_checks (listing_id, reason, requested_at)`, si el auto no tiene señal de vida hace más de 6 h. El worker la atiende en menos de un minuto con prioridad máxima. Si sale `gone`, la próxima vista ya muestra «Ya no está disponible». La web no hace requests a la fuente.

- **Señal:** la página de detalle.
- **A quién prioriza:** exactamente lo que el usuario está mirando.
- **Cadencia:** casi en tiempo real, con un tope por fuente por hora (por ejemplo ML 60 y FB 10).
- **Costo:** bajo, decenas por día (88 clics en 14 días).
- **Cambios:** una migración con la tabla, RLS y un RPC `request_availability_check`; una llamada desde la web; una tarea nueva del worker o un tick de 60 s; `app_config.availability_on_view`.
- **Qué mueve:** M2. La primera visita igual puede llegar al auto muerto, porque el chequeo corre en paralelo. Sirve más como complemento que como solución.
- **Esfuerzo:** medio, 2 o 3 días.
- **Cómo se revierte:** `enabled: false`.

### Combinaciones

- **B + D interna + A (recomendada):**
  - B hace el trabajo de detectar, con prioridad en lo que el usuario ve.
  - D (solo la columna) mejora el orden y el back-off de B y permite medir M3.
  - A es barata y cierra `price_drop` y los resúmenes, el único hueco medible en mails.
- **Sin etiqueta, FB es el hueco:** su cupo tiene que ser chico por la sesión. Para cubrirlo sin
  bajar la calidad, la prioridad de B pone primero los autos de FB que el usuario tiene más a la
  vista (`high`, oportunidades, primeras posiciones de sus búsquedas, usuarios que pagan) y E cubre
  el que abre un auto puntual.
- **C** solo para las fuentes httpx de bajo riesgo o con la API de ML. Es higiene del inventario, no urgencia del usuario; se puede hacer más adelante.
- **E** si después de B siguen apareciendo clics en autos muertos, sobre todo de FB.

---

## 6. Tabla comparativa

| | A. Antes de enviar | B. Re-chequeo por valor | C. Barrido total | D. Columna interna | E. Al mirar |
|---|---|---|---|---|---|
| Ataca | Mails (M1) | Panel y demora (M3, M4) | Inventario (M4, limpieza) | Orden de B y medición | Clic (M2) |
| Señal | Detalle | Detalle | Detalle o API de ML | Ausencia, solo para priorizar | Detalle |
| Requests por día | ~100 | ML hasta ~3–4 k al inicio, después cientos; FB ~480 | ML ~6,5 k (o ~330 con API); otras ~4,6 k | 0 | Decenas |
| Riesgo de bloqueo | Bajo | Medio en ML, controlado por cupo | Alto en ML sin API; FB excluido | Ninguno | Bajo |
| Impacto esperado | M1 0,3 % → ~0,05 % | M3 32 % → <5 % (ML y otras); M4 ML 15 d → <2 d | M4 en fuentes barridas | Nada visible; B rinde más | M2 → ~0 |
| Cambia lo que ve el usuario | Solo saca mails muertos | Solo saca autos muertos | Solo saca autos muertos | No | Solo saca autos muertos |
| Migración | No | No (mejor con la de D) | No | Sí (columna) | Sí (tabla y RPC) |
| Interruptor | `availability_presend` | `watchlist_matched` | `inventory_sweep` | — | `availability_on_view` |
| Esfuerzo | 1–2 días | 2–3 días | 2–4 días | 1 día | 2–3 días |
| Costo en $ | 0 | 0 | 0 (API de ML: app gratis) | 0 | 0 |

## 7. Recomendación

**Hacer B, con la columna interna de D y A para `price_drop`, en este orden.** El usuario nunca ve un estado intermedio: el auto está vigente o «Ya no está disponible».

1. **Paso 0, sin código, con OK de Juan.** Crear la fila `app_config.watchlist_matched` con `per_source` 60 (el código actual solo acepta un número para todas las fuentes). Durante 48 h, mirar las pausas del breaker de ML y de FB.
   - Con 60 por hora en FB son 30 min por hora de sesión, demasiado. Una alternativa es dejar 20 y excluir FB recién en el paso 1.
   - Ganancia: la cola de ML de búsquedas vivas baja varias veces más rápido, sin deploy.
2. **Paso 1 (B + columna de D).** Cupo por fuente, prioridad por lo que el usuario tiene a la vista, solo búsquedas `enabled`, tick de 15 min y back-off apoyado en `alive_checked_at`.
3. **Paso 2 (A).** Chequeo en vivo antes de enviar, solo para `price_drop` y los ítems de resumen viejos.
4. **Medir M1–M5** una semana antes y una después. Si siguen apareciendo clics en autos muertos de FB, sumar **E**.

**Por qué.** Los datos muestran que el mail ya sale limpio (0,3 %) y que lo roto es el panel (32 % dudoso) y la demora de ML (15 días). Eso se arregla con ritmo y prioridad, que es B, sin fuentes nuevas, sin costo y sin tocar cómo se ve el panel. C es caro en ML y no mejora lo que ve el usuario.

**Lo que queda flojo:** FB. Con cupo chico, sus autos de menor prioridad pueden seguir viéndose vigentes unos días después de terminar. Sin la etiqueta, la única forma de achicar eso es más cupo de FB (riesgo para la sesión) o E.

## 8. Decisiones de Juan (2026-11-25)

1. **ML: 150 páginas de detalle cada 15 min** mientras se vacía la cola. Se baja desde `app_config` si el breaker pausa ML.
2. **FB: cupo chico** (unas 5 cada 15 min, primero lo que el usuario tiene más a la vista). Se acepta que el resto de FB tarde días en marcarse terminado.
3. **API de ML: sí, evaluarla.** Prueba hecha el mismo día sin token:
   - `GET api.mercadolibre.com/items?ids=…` responde **401**;
   - `GET api.mercadolibre.com/items/<id>` responde **403** (`PA_UNAUTHORIZED_RESULT_FROM_POLICIES`).

   Conclusión: **pide token**. Para usarla hay que crear una app de desarrollador de ML (gratis) con una cuenta de Juan y guardar en el VPS un token que se renueva solo con su `refresh_token`. Falta confirmar, ya con el token, que el multiget devuelve `status` de avisos de otros vendedores. Si funciona, el chequeo de ML pasa por la API en vez de la página, y la Opción C (barrido de todo ML) se vuelve barata (~330 requests por día).
4. **Búsquedas apagadas: afuera.** La cola de re-chequeo solo toma matches de búsquedas `enabled`.

**Plan resultante:**
- Paso 0 se descarta: hoy `per_source` es un solo número para todas las fuentes, y 150 aplicado a FB serían 75 min de sesión por hora. Las decisiones de cupo necesitan el código del paso 1.
- Paso 1: B con cupo por fuente (ML 150, FB 5, resto 40, cada 15 min), solo búsquedas `enabled`, prioridad y back-off, más la columna interna de D.
- Paso 2: A para `price_drop` y resúmenes.
- Paso 3: Juan crea la app de ML; se prueba la API y, si sirve, reemplaza la página en los chequeos de ML.

## 9. Preguntas que quedaron (ya respondidas, ver §8)

1. **Cupo en ML:** ¿OK subir hasta unas 150 páginas de detalle cada 15 min (20 min de carril por hora) mientras se vacía la cola, y bajar si el breaker pausa? ¿O preferís empezar en 60?
2. **Facebook:** ¿aceptás que FB quede con cupo chico (unas 5 cada 15 min, primero lo que el usuario tiene más a la vista), sabiendo que el resto de FB puede tardar días en marcarse terminado? ¿O preferís arriesgar más la sesión con más cupo?
3. **API de ML (`items`):** ¿querés que se evalúe? Si pide token, hay que crear una app de desarrollador de ML (gratis, pero es una cuenta nueva a tu nombre). Es un cambio de fuente.
4. **Búsquedas apagadas:** ¿OK dejar de re-chequear matches de búsquedas `enabled = false`? Hoy gastan cupo.
