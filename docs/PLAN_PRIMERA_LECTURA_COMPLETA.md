# Plan: primera lectura completa del modelo buscado

Fecha: 2026-11-16. Estado: fases 1 a 3 implementadas detrás de `STOCK_READ` (ver «Implementación»), sin desplegar.

## Problema

Una búsqueda nueva debería mostrar todo lo que hay publicado del modelo, no solo lo
reciente. Hoy en Mercado Libre no pasa. Caso: búsqueda 558 (Renault Clio 1990–2000,
rojo) y el aviso MLA-2124030699 (Clio 1997 rojo, publicado hace 53 días), que nunca
entró en la base.

## Qué hace el sistema hoy

| Fuente | Primera lectura | Lecturas siguientes |
|---|---|---|
| Mercado Libre | Solo avisos de los últimos 30 días (`_recency.target_window`) | «Publicados hoy», cada 30 min |
| Facebook | Últimos 30 días | Último día |
| Las demás (deRuedas, Rosario Garage, Kavak…) | Stock completo | Stock completo |

Tres huecos en Mercado Libre:

1. **Lo publicado hace más de 30 días nunca entra.** Ni en la primera lectura.
2. **Una búsqueda que se suma a un modelo ya seguido no dispara ninguna lectura.**
   El target Clio existía desde el 29/10 para otras búsquedas. Cuando la 558 lo
   ensanchó a 1990, `first_run_done` no se reinició (solo lo hacen un cambio de
   política o de cobertura, `targets.sync_targets`). Para 1990–2000 no hubo ni
   siquiera la lectura de 30 días: solo entra lo publicado desde el 14/11.
3. **La lectura completa de cada 48 h ya baja todas las tarjetas y las tira.**
   `MercadoLibreScraper.full_read` recorre el stock entero para los comparables y
   solo guarda los IDs. Clio: 875 listados, 282 guardados.

Medición de las lecturas completas de los últimos 3 días (57 modelos): ~33.500
avisos listados contra ~12.400 guardados. Guardamos cerca del 37 % del stock de ML.

## Opciones

### A. Que la lectura completa guarde lo que lee (recomendada)

`full_read` devuelve las tarjetas además de los IDs y se ingieren como stock viejo:
se ven en la web, nunca se notifican.

- A favor: cero requests extra a ML en el ciclo de 48 h, porque esas páginas ya se
  bajan. Cubre el hueco 1 para todos los modelos.
- En contra: la base crece. Estimado +21.000 avisos de ML (27.000 → ~48.000),
  unos +80 MB en `listings`. La base está en 1.009 MB.
- Sola no alcanza: una búsqueda nueva esperaría hasta 48 h.

### B. Ensanchar la ventana de la primera lectura (30 → 180 días)

- En contra: esa lectura fecha cada aviso abriendo su página (8 s cada una, tope
  200 por pasada). Clio serían horas y cientos de requests. No resuelve el hueco 2.
- Descartada.

### C. Lectura de stock al crear o ensanchar una búsqueda

Al entrar una búsqueda, leer enseguida el stock de los años que el target todavía
no cubrió, con la misma lectura de A.

- A favor: la búsqueda nueva ve el panorama en minutos. Lee solo lo que falta.
- En contra: requests extra a ML por cada búsqueda que ensancha un modelo
  (1 página cada 48 avisos; Clio 1990–2000 son 1 o 2 páginas).

**Recomendación: A + C.** A mantiene el stock al día sin costo de requests; C lo
adelanta para la búsqueda que recién llega.

## Diseño propuesto

### 1. Cobertura de stock por target

Cada target de ML guarda qué rango ya leyó entero: `query._stock = {year_min,
year_max, km_max, at}`. Es el mismo patrón que `query._read` usa en las fuentes
sin fecha (`pipeline/news.py`).

### 2. Cómo se mezcla con las búsquedas que se van sumando

| Caso | Qué pasa |
|---|---|
| Modelo nuevo (target nuevo) | Primera corrida: lectura de stock completa + ventana de 30 días como hoy (da las fechas). |
| Búsqueda nueva dentro del rango ya cubierto | Sin requests. Se arma desde lo guardado, al instante. |
| Búsqueda nueva que ensancha años o km | Lectura de stock solo de los años que faltan, en la próxima corrida del target, saltando la espera de 48 h. |
| Ciclo de 48 h | Igual que hoy, pero guarda lo nuevo que encuentre. |

El costo sigue siendo por modelo y no por búsqueda: la décima búsqueda de Clio no
cuesta nada.

### 3. Qué ve el usuario

- Los avisos de stock entran como «ya publicado»: aparecen en la web y en el mail
  de bienvenida, sin alerta.
- No tienen fecha de publicación (la tarjeta de ML no la trae). Hoy `rematch`
  toma los avisos guardados de los últimos 30 días por fecha de detección; hay
  que pasarlo a «activo y visto en la última lectura completa».
- El cupo de 50 por búsqueda sigue vigente: con más stock, importa más que el
  orden sea por puntaje.

### 4. Riesgos a cuidar

- **Días publicados y estadísticas de mercado.** Un aviso de 53 días entraría
  con `first_seen_at` de hoy. Hay que marcarlo (`attributes._not_news =
  'stock'`) y dejarlo fuera de los cálculos de antigüedad en `market_stats`.
- **Comparables.** Más avisos activos reales mejoran la referencia de precio,
  pero conviene revisar antes y después en 3 o 4 modelos.
- **Detalle y costos de IA.** Los avisos de stock no deben disparar por sí solos
  la bajada de detalle, la visión de color ni el LLM de descripción; solo los
  que matchean una búsqueda, con los topes diarios actuales.
- **Límite de 42 páginas de ML.** Un modelo grande ya se lee año por año; un año
  con más de 2.016 avisos queda incompleto y se registra, como hoy.
- **Facebook queda igual.** No tiene forma de leer stock completo; sigue en 30
  días.

## Fases

1. **Guardar el stock en la lectura completa** (opción A). `full_read` devuelve
   tarjetas, ingest como stock viejo, marca `_not_news`, `query._stock`. Tests del
   colector y de `crawl`. Detrás de un interruptor (`FULL_READ_STORE`).
2. **Lectura al crear o ensanchar** (opción C). Detección del rango faltante en
   `sync_targets`, lectura por años faltantes, prioridad en la cola del carril.
3. **Rematch desde el stock.** La búsqueda nueva se arma con todo lo activo
   guardado, no con 30 días. Revisar el mail de bienvenida.
4. **Medición.** Antes y después: avisos guardados por modelo, matches en la
   primera hora de una búsqueda nueva, requests a ML por día, tamaño de la base.

Sin migración de esquema: todo vive en `crawl_targets.query` y
`listings.attributes`.

## Decisiones de Juan (2026-11-16)

1. **Alcance:** se guarda todo el rango del modelo; sirve a otras búsquedas.
2. **Antigüedad:** todo aviso activo, sin corte.
3. **Arranque:** primero los modelos más buscados, pero tiene que alcanzar a
   todos. Tope `STOCK_READ_TARGETS` = cuántos targets por fuente, ordenados por
   cantidad de búsquedas, leen stock; 0 = todos. Se despliega en 10 y se sube a 0.
4. **Fuentes:** también Facebook y V6.

## Facebook

Hoy pide `daysSinceListed` = 30 como máximo. La lectura de stock es la misma
búsqueda sin ese parámetro, ordenada por fecha, con los años del target.

- Las fechas salen de los datos del feed (`FB_FEED_DATES`), sin abrir la página
  de cada aviso. Lo que el feed no fecha se guarda sin fecha, como stock.
- Solo en la primera corrida de un target y cuando una búsqueda lo ensancha.
  No en un ciclo fijo: la sesión de Facebook es frágil y cada lectura larga
  suma riesgo de bloqueo.
- Con tope de scrolls propio; si lo alcanza, queda parcial y sigue en la
  próxima corrida. Respeta el breaker de la fuente.
- Facebook busca alrededor de una ciudad (la de la búsqueda más vieja del
  target). Esa limitación queda igual.

## V6

V6 ya lee el sitio entero en cada corrida desde el 06/11 (target de inventario:
~128 autos por lectura, 204 activos guardados). No hay lectura que agregar.
Lo que sí le toca es la fase 3: que una búsqueda nueva se arme con todo ese
stock guardado. Se cubre con un test.

## Contrato entre colector y crawl

Un colector que puede leer su stock expone:

```python
async def stock_read(self, filters: dict) -> SearchResults
```

- `filters`: `marca`, `modelo`, `anio_min`, `anio_max`, `km_max` (y
  `origin_lat`/`origin_lon` en Facebook). Sin ventana de publicación.
- Devuelve las tarjetas como `Listing` (`published_at` solo si la fuente lo da),
  con `complete` y `reason` como cualquier `SearchResults`.
- `pipeline/crawl.py` lo llama (por `isolated_call` si el colector es
  `ISOLATED`), ingiere el resultado como stock viejo y actualiza `query._stock`
  solo si la lectura fue completa.

## Sesiones de implementación (Opus 5.5, esfuerzo medio)

| Sesión | Alcance | Archivos |
|---|---|---|
| Núcleo + Mercado Libre | Fases 1 a 3, tope de arranque, test de V6 | `pipeline/crawl.py`, `pipeline/rematch.py`, `pipeline/news.py`, `db/repos/targets.py`, `collectors/mercadolibre.py`, `config.py` |
| Facebook | `stock_read` del colector y sus tests | `collectors/facebook.py` |

Cada una en su worktree desde `origin/main`, termina en un PR sin mergear. El
deploy y prender el interruptor en producción esperan el OK de Juan.

## Implementación (fases 1 a 3, rama `claude/stock-read-core-ade663`)

Lo que cambió respecto de la propuesta, siguiendo el código:

- **Un solo interruptor, `STOCK_READ`** (no `FULL_READ_STORE`), con
  `STOCK_READ_TARGETS` (por defecto 10). Apagado, `crawl._run_one` llama a
  `full_read` como hoy y nada más cambia (rematch incluido).
- **Contrato `stock_read(filters) -> SearchResults`** en Mercado Libre: la misma
  caminata de `full_read`, que guarda las tarjetas; el resultado trae `listed`
  (todos los IDs, para `record_full_read`) y `pages`. Con el target dentro del
  tope, la lectura de 48 h **es** la lectura de stock: una sola caminata.
- **Cuándo** (`crawl.stock_reads`): sin `query._stock` (target nuevo, o el
  primero desde que se prende el interruptor), cuando el rango del target sale
  de `_stock` (solo los años que faltan; km más amplio = rango entero), y en el
  ciclo de 48 h de ML. Nunca carrocería, solo-conteo ni inventario (V6). Una por
  fuente cada `FULL_READ_SPACING_SECONDS`, compartida con las lecturas
  completas. Una lectura parcial guarda lo leído y reintenta a las 6 h
  (`query._stock_tried`). La «prioridad en la cola del carril» no hizo falta: la
  lectura corre en la próxima corrida del target (cada 30 min).
- **No silenciar novedades**: la lectura de stock no guarda las tarjetas con
  fecha de las últimas 25 h ni, en ML, las numeradas por encima del aviso más
  nuevo de su serie que conocen las lecturas por fecha
  (`targets.news_watermarks`): son de después de la corrida y les toca a
  «Publicados hoy».
- **Marcas**: `_not_news.reason = 'stock'` (`news.STOCK`, dentro de `MUTED`):
  backfill para toda búsqueda, nunca contado en 2.5. El lote de stock pasa por
  `scheduler.process_batch(stock=True)`: todo backfill, sin visión de color
  previa; bajadas de precio y avisos terminados sí avisan como en cualquier
  corrida.
- **Rematch**: con el interruptor, `recent_active(confirmed=True)` toma lo visto
  en 30 días por una corrida **o** por una lectura completa
  (`last_full_seen_at`) y saca lo que una lectura completa posterior ya no vio
  (`listing_unconfirmed`, como los comparables).
- **Efectos laterales**: `near_zone` no toma stock como auto nuevo; el puntaje
  de recencia de un aviso de stock sin fecha es «desconocido»;
  `enrichment_queue` no encola stock sin match por precio parcial ni por banda;
  `market_stats` ya dejaba fuera de días y de «nuevos» a lo marcado
  `_not_news` sin fecha.
