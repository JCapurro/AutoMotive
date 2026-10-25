# Carrocería

Pedido de Juan del 15/10/2026: sumar la carrocería a la búsqueda (sedán, hatchback, SUV y las demás) y recolectarla de las fuentes para poder filtrar.

- **Prueba gratis (`free`).** La carrocería es un filtro opcional **dentro del modelo**, como la caja o el combustible.
- **Particular (`pass`) y Pro (`pro`), y los admins.** Además pueden buscar **sin modelo, solo por carrocería**: por ejemplo, «cualquier SUV hasta USD 20.000». Es la función de plan `model_less_search`.

## Categorías

Una sola lista, con el mismo orden y los mismos códigos en la base, el worker, el LLM y la web:

| Código | Etiqueta |
|---|---|
| `sedan` | Sedán |
| `hatchback` | Hatchback |
| `suv` | SUV |
| `pickup` | Pick-up |
| `rural` | Rural |
| `monovolumen` | Monovolumen |
| `coupe` | Coupé |
| `convertible` | Convertible |
| `utilitario` | Utilitario |

- Ningún código es parte de otro (`_choice` del matching compara con `in`).
- Crossover y Off-Road van a `suv`; Cabriolet y Roadster, a `convertible`; Minivan, a `monovolumen`; Furgón y Van, a `utilitario`.
- «Camioneta» sola no dice nada (puede ser SUV o pick-up) y queda sin carrocería.

### Valores de cada fuente

| Fuente | Dónde | Crudo → código |
|---|---|---|
| Mercado Libre | Ficha: «Tipo de carrocería» y JSON-LD `bodyType`. Búsqueda: filtro `VEHICLE*BODY*TYPE` | 452758 Sedán→`sedan` · 479344 Hatchback→`hatchback` · 452759 SUV, 452761 Crossover, 452754 Off-Road→`suv` · 452756 Pick-Up→`pickup` · 452760 Rural→`rural` · 452752 Monovolumen, 452753 Minivan→`monovolumen` · 452749 Coupé→`coupe` · 452748 Cabriolet, 452757 Roadster→`convertible` · 452750 Furgón, 452755 Van→`utilitario` · 452751 Light Truck→sin carrocería |
| Kavak | Slug de la tarjeta (`…-{carroceria}-{año}`), la etiqueta con que termina el título («… Hatchback 2023»), JSON-LD `bodyType` de la ficha, listado `/ar/usados/{carroceria}` | `sedan`, `hatchback`, `suv`, `pickup`/`pick-up`, `minivan`/`monovolumen`→`monovolumen`, `wagon`/`rural`→`rural`, `coupe`, `cabriolet`/`convertible`→`convertible`, `furgon`/`van`→`utilitario`; `camioneta` y lo desconocido → sin carrocería. La etiqueta del título es el dato de la fuente, no una palabra del vendedor: un catálogo de una sola carrocería le gana (Kavak pone «Hatchback» a la Spin y «Wagon» a la Suran) |
| V6 | Ficha: «Categoría» | Vocabulario de Mercado Libre |
| Autocosmos | Ficha: `<meta name="dfp_segmentoNick">`; búsqueda `?s=N` | 1 hatchback · 2 sedan · 3 utilitario · 4 monovolumen · 5 convertible · 6 suv · 7 pickup · 8 coupe · 9 «Familiar» rural |
| Car One | `carone_type_data.label` | `SEDAN`→`sedan` y el resto por palabra clave; «Familiar» → sin carrocería |
| Grupo Randazzo | «Tipo de vehículo», sin el sufijo de segmento («Pick-up B») | Por palabra clave, salvo «Sedan» (también los hatchback: Argo, 208, Onix) y «Wagon (obsoleta)» (también SUV: Kardian), que no dicen nada: deciden el título, las puertas y el catálogo |
| Usados Santa Fe | `tipo` | `SUV`, `Pickup`, `Furgón`/`Utilitario`; `Auto`/`Camioneta` → sin carrocería |
| Mardel Usados | `data-tipo` | `Utilitario`→`utilitario`; `Auto`/`Camioneta` → sin carrocería |
| Autocity | Ficha: primer tramo de `.firstOne` | Por palabra clave |
| deRuedas, Rosario Garage, Facebook, Instagram | Solo grupos gruesos o nada | Título y catálogo |

## Cómo se decide la carrocería de un aviso

`worker/normalization/body_type.py`, en el estilo de `transmission.py`. Se guarda en `listings.body_type` (código o `null`) y el origen en `listings.attributes._body_type = {"method", "raw"}`. El orden:

1. **Palabras explícitas en la versión o el título**: «sedán», «hatchback», «pick up», «cabina doble», «rural», «weekend», «variant», «SW» (no «SW4»), «coupé», «cabrio», «furgón», «monovolumen»… y las reglas por submodelo (Duster **Oroch** → pick-up, Palio **Weekend** → rural, Gol **Country** → rural, C4 **Grand Picasso** → monovolumen, Onix **Plus** → sedán…). Ganan siempre: el catálogo resuelve esos submodelos al modelo padre.
2. **El dato estructurado de la fuente** (`Listing.carroceria`, crudo o ya en código; en Kavak también la etiqueta del final del título y el slug de la URL). Se acepta si el catálogo no conoce el modelo o si el valor está entre las carrocerías del modelo. Si el modelo tiene una sola, gana el catálogo: las fuentes tienen ruido (Mercado Libre pone SUV a la Spin y Kavak, Hatchback). Solo se leen las URL de Kavak (carrocería) y Autocity (puertas): las de Mercado Libre son listas de palabras para buscadores.
3. **Puertas** (3p/5p → hatchback, 4p → sedán), solo para elegir entre las carrocerías del modelo.
4. **El catálogo**, si el modelo tiene una sola carrocería.
5. Si no, sin carrocería.

Trampas conocidas: «Cross» no es SUV (Etios Cross, Suran Cross) salvo Corolla Cross, que es otro modelo; «HB» dentro de HB20; «CD» suelto es la radio; «4x4», «jeep» y «camioneta» no definen nada; «familiar» no significa nada (salvo el segmento 9 de Autocosmos); «CC» después del modelo de Peugeot (207 CC) es el coupé-cabriolet, después de la cilindrada («1600 cc») no; «Coupé»/«Sportback» después de una SUV (X6, GLC, Q3, Q4 e-tron, Cayenne) es SUV, pero no si en el medio hay otro modelo («Q5 Q8 A7 Sportback»).

`vehicle_catalog.body_types text[]`: las carrocerías posibles del modelo, de la más común a la menos común. Un solo valor = seguro.

`body_type` no entra en `KEY_ATTRS`: completarla no genera un snapshot ni un `listing_updated`.

## Búsqueda

`search_profiles.filters.body_types`: lista de códigos. Se omite si está vacía.

- **Dentro del modelo** (todos los planes): un aviso sin carrocería da `unknown` (no descarta, baja el puntaje), igual que la caja. La web muestra el selector solo si el modelo tiene dos carrocerías o más en el catálogo, y ofrece solo esas.
- **Sin modelo** (`model_less_search`): `filters` sin `make` ni `model` y con al menos una carrocería. Exige `price_max`. Un aviso sin carrocería da `fail`: si no, «cualquier SUV» coincidiría con todo aviso sin dato.
- Las dos reglas valen igual en `matching.py` y en `preview_search`; si no, el conteo en vivo miente.
- La razón del matching es `body_type` y va después de `fuel`.
- Nombre automático: «SUV hasta USD 20.000», «SUV o Pick-up hasta $ 25.000.000».

### Función de plan

- `app_config.plan_limits.pass.model_less_search = true` y lo mismo en `pro`. Los admins la tienen siempre (`plan_feature`).
- La base es el control final, en dos capas:
  - el trigger de `search_profiles` rechaza guardar habilitada una búsqueda sin modelo sin la función (`plan_feature_unavailable`, 42501), sin carrocería (`search_needs_model_or_body_type`, 22023) o sin precio máximo (`search_needs_max_price`, 22023);
  - `search_access_active` da `false` a una búsqueda sin modelo de una cuenta sin la función, así que deja de rastrearse, matchearse y avisar.
  - «Sin modelo» es una sola regla en la base (`search_is_model_less`) y en el worker (`matching.model_less`): `make` y `model` ausentes, `null` o texto en blanco. El trigger rechaza (`invalid_filters`, 22023) un `make`/`model` que no sea texto o `null` y `body_types` que no sea una lista de textos, así nadie se saltea el control de plan con `{"make": false}`.
- La web pregunta con `my_plan_feature('model_less_search')`.
- La prueba gratis ve una línea: «Con Particular o Pro también podés buscar por carrocería, sin elegir modelo.», con link a los planes.
- El conteo después del vencimiento (2.5) no incluye búsquedas sin modelo.

## Rastreo sin modelo

- `crawl_targets.body_type`: un target por (fuente, carrocería), sin marca ni modelo. La clave única pasa a ser `(source, make, model, body_type)`.
- `app_config.body_type_targets = {"sources": ["mercadolibre", "kavak"], "interval_seconds": 1800}`, editable en /admin/config. Además, cada collector declara `BODY_TYPES`, las carrocerías que sabe buscar.
  - **Mercado Libre:** siempre «Publicados hoy» (también la primera vez), con el año y el km más amplios de las búsquedas en la URL (el año, ensanchado por la banda de referencia). Cada código va a sus ids (`suv` = SUV + Crossover + Off-Road). El sello de carrocería se pone solo si la página confirma el filtro aplicado (`applied_filters`); si no, la corrida falla, porque ML ignoraría el filtro y traería todo.
  - **Kavak:** `/ar/usados/{carroceria}`.
- Las fuentes que ya se leen enteras (Car One, Randazzo, Santa Fe, Mardel, Autocity, Instagram) no necesitan target nuevo.
- **Antes de guardar**, un target por carrocería descarta los avisos que ninguna de sus búsquedas puede querer: precio en USD por encima del tope más alto, año por debajo del más bajo menos la banda de referencia (`query.year_band`, TECHNICAL_PLAN.md 5.1: guarda un año más abajo para los comparables, que ninguna de sus búsquedas matchea) y km por encima del más alto. Los datos desconocidos pasan. Así la base (Supabase Free, 500 MB) crece con lo que se busca y no con todas las SUV del país.
  - En una fuente sin fecha de publicación (Kavak) cada corrida relee todo el stock de la carrocería, así que el target recuerda lo que descartó en su última corrida completa (`crawl_targets.prefilter_rejected`). Si después lo guarda (una búsqueda más amplia, una baja de precio, la cotización), es stock viejo: backfill, sin aviso. En un target de Facebook por modelo esa columna guarda otra cosa, su memoria de fechas (RECENT_PUBLICATIONS.md); Facebook no tiene targets por carrocería, y `pipeline/crawl.py` (`_date_memory`) solo la usa así en Facebook sin carrocería.
- **Cada lote**, de cualquier target, se matchea también contra las búsquedas sin modelo. Una SUV que trajo el target del Corolla Cross, de Facebook o de deRuedas le llega a «cualquier SUV».
  - La primera corrida de un target que no es de la búsqueda (un modelo nuevo, una fuente recién habilitada) no la silencia: lo publicado hace poco es novedad y se avisa como en cualquier lote; lo viejo o sin fecha de publicación (no se distingue del stock) queda como backfill. Silenciarlo lo perdería: el target por carrocería lee solo el último día y las corridas siguientes, solo lo publicado después.
  - Un aviso guardado antes al que este lote le completó o corrigió la carrocería es backfill para las búsquedas sin modelo, no un aviso nuevo.
- **Una búsqueda sin modelo nueva o editada** se matchea contra lo guardado de los últimos 30 días, de todas las fuentes, con un prefiltro SQL (carrocería, año, km y precio). Queda como backfill, sin avisos. Solo los 300 avisos más nuevos que pasan los filtros piden comparables (una llamada a `comparables()` cada uno, mientras el tick espera); el resto queda sin precio de referencia hasta el re-puntaje nocturno.
- **Cuando la ficha completa o corrige la carrocería** de un aviso, ese aviso se matchea contra las búsquedas sin modelo y se re-puntúan sus matches.

## Datos existentes

- Las migraciones: `20261030110000_opportunity_threshold_grant.sql` (un arreglo aparte, ver abajo), `20261030120000_body_type.sql` (columnas, funciones, trigger) y `20261030120100_catalog_body_types.sql` (el catálogo). Van después de `20261029120000_email_only_accounts.sql`, que ya está en main.
- `python -m tools.backfill_body_type` recalcula `body_type` de los avisos guardados, por lotes, con lo que ya hay en la base: título, versión, `attributes` de las fichas y catálogo. **Tiene que correr antes de que el worker y la web con búsqueda sin modelo queden en producción**: si no, cada lote que vuelve a ver un aviso viejo le completa la carrocería (eso ya es backfill, pero lo matchea recién ahí) y la búsqueda nueva arranca con menos resultados de los que tiene.
- Después, `python -m tools.reprocess --raw --outdated --source <fuente>` re-parsea las fichas guardadas de las fuentes cuyo parser cambió.

### Orden del pase a producción

No hay un orden en el que convivan el código viejo y la base nueva, ni al revés: el `sync_targets` viejo hace `ON CONFLICT (source, make, model)` y la migración cambia esa clave única a `(source, make, model, body_type)`; el worker y la web nuevos leen y escriben columnas que solo existen después de la migración. Entonces, con el OK de Juan:

1. Antes, por separado y cuanto antes: `20261030110000_opportunity_threshold_grant.sql`. Arregla un error de hoy en producción (editar una búsqueda desde la web falla con «permission denied» por la columna `opportunity_threshold_pct`) y no depende del resto. Primero mirar si ya está: `select has_column_privilege('authenticated', 'public.search_profiles', 'opportunity_threshold_pct', 'UPDATE')`.
2. Parar el worker del VPS.
3. Mirar `max(version)` de `supabase_migrations.schema_migrations` en producción y aplicar las dos migraciones de carrocería, cada archivo en una transacción con el insert de su versión exacta.
4. Desplegar el worker nuevo en el VPS y correr `python -m tools.backfill_body_type` (y el `reprocess` de arriba) antes de arrancarlo.
5. Recién entonces mergear a main y pushear, para que Vercel despliegue la web. No mergear a main antes de que la migración esté aplicada en producción.
