# Valor justo por auto · referencia de precio por año, versión y km

Fecha: 2026-11-20. Estado: **borrador para que Juan lo apruebe**. No hay nada implementado ni ninguna migración escrita. No se tocó producción: todo se midió con SELECT de solo lectura, y la única función llamada fue la STABLE `comparables()`.

Pedido de Juan: revisar el criterio del score en las búsquedas generales (un modelo entero), porque «no siempre a mayor año mejor auto: un 2018 full es mejor que un 2021 base». Después: «lo más importante es que el score sea más inteligente y use [el presupuesto] en contexto junto a los demás datos». Aprobó diseñar «el valor justo por auto, con el presupuesto como prueba encima».

**Base de código:** `origin/main` (8be3e74, 20/11). Las líneas y los archivos citados son de ahí. La definición vigente de `comparable_listings()` está en `20261228120000_dealer_program.sql`; la de `comparables()`, en `20261215120000_comparables_price_floor.sql`.

Anexo: [`2026-11-20-valor-justo-backtest.sql`](2026-11-20-valor-justo-backtest.sql), las consultas de la medición.

## Resumen

- **Qué es.** Para cada auto, cuánto vale según su año, su versión, sus km y su caja, calculado con todos los avisos de su modelo. Hoy el score compara contra «gemelos» (mismo modelo, año ±1, km ±25 %, misma versión y caja si hay 5); cuando no hay 5 de la misma versión, compara contra todas las versiones mezcladas.
- **Por qué.** Eso último pasa en el 42 % de los matches. Ahí las versiones base y los autos con muchos km parecen baratos, y las versiones full parecen caras.
- **Qué gana.** Con autos que el cálculo no vio, el valor justo empata con los gemelos cuando los hay y baja el error cuando no los hay: en Hilux de 10,7 % a 6,7 %, en Amarok de 16,5 % a 8,0 %.
- **Cómo entra.** Regla híbrida: si hay gemelos de la misma versión, se usan como hoy; si no, se usa el valor justo. Y solo en los modelos donde el valor justo le gana a la referencia actual, medido en cada corrida.
- **Cómo sale.** Primero en sombra: se calcula y se guarda al lado, sin cambiar ningún score, nivel, alerta ni texto. Pasa a real con otro PR y con criterios fijados acá.
- **El presupuesto.** Hoy no hay evidencia de que la gente prefiera los autos cercanos a su tope (§6). En la sombra se guarda, para cada búsqueda con tope, cuánto vale el auto contra ese tope, y se mide con el control correcto. Cambiar el orden con eso queda como prueba aparte.
- **Costo.** Una migración (dos tablas, una función, una clave de config), un job diario del worker y un informe. USD 0 de infraestructura.

## 1. Problema, medido

Búsquedas de los últimos 30 días (738) y matches de los últimos 14 (36.732), el 20/11/2026.

| hecho | valor |
|---|---|
| búsquedas sin versión y con año amplio o sin año | 257 de 738 (35 %) |
| de esas, sin precio | 120; juntan el 39 % de los matches (153 por búsqueda, hasta 1.111) |
| referencia con gemelos de la misma versión y caja | 58 % de los matches |
| referencia con versiones mezcladas (nivel `transmission` o `model`) | 42 % (19,5 % + 22,3 %) |
| correlación entre el descuento y la prima de la versión, en esos dos niveles | −0,44 y −0,18 (con gemelos: −0,01) |
| correlación entre el descuento y los km, Gol Trend, en esos dos niveles | −0,40 y −0,43 (con gemelos: −0,05) |
| «baratos» (10 % o más debajo) que no lo son al ajustar por versión / ofertas reales tapadas | 97 / 227, solo entre los autos con versión evaluable |

Cuánto vale un año contra cuánto vale la versión cambia por modelo, así que ninguna regla fija sirve:

| modelo | un año vale | de la versión más barata a la más cara | equivale a |
|---|---|---|---|
| Gol Trend | 6,1 % | 7,5 % | 1,2 años |
| Corolla | 7,8 % | 18,2 % | 2,2 años |
| 208 | 6,9 % | 28,6 % | 3,8 años |
| Hilux | 5,5 % | 39,3 % | 6,2 años |
| Amarok | 7,2 % | 54,0 % | 6,2 años |

Lo que el score hace hoy con año y km: nada. Dentro de una misma búsqueda, el score promedio es 65,0 / 65,0 / 63,7 por tercio de año (viejo a nuevo) y 63,6 / 64,9 / 64,5 por tercio de km (pocos a muchos).

## 2. Objetivo

1. Que «X % debajo» compare cada auto contra lo que vale ese auto, también cuando no hay gemelos.
2. Dejar medido si el presupuesto, usado junto con el valor del auto, predice lo que la gente abre.

**No es objetivo de este diseño:**
- Cambiar la fórmula del score (f2 o f3), los niveles o los textos.
- Sumar puntos por año más nuevo o por versión más alta.
- Pedir el presupuesto en el alta, mostrar la lista por franjas, aprender de los clics.
- Tocar la referencia del panel de agencias (`dealer_market_ref`, del 20/11), que tiene su propia cascada por versión y km.

## 3. El valor justo

### 3.1 Fórmula

Por modelo (marca + modelo), en logaritmos del precio en dólares:

```
ln(valor) = A[año] + G[versión] + H[caja] + B · (ln(km) − KM[año])
```

- `A[año]`: el nivel de precio de ese año.
- `G[versión]`: la prima de la versión contra la versión típica (Highline +, Trendline −). 0 si el aviso no trae versión o la versión tiene pocos avisos. La clave es `lower(trim)`, la misma con la que hoy se definen los gemelos.
- `H[caja]`: la prima de la caja (manual o automática). 0 sin dato.
- `B`: cuánto baja el precio al subir los km. `KM[año]` es el km típico de ese año. 0 sin km.

Medido: `B` = −0,141 en Gol Trend (el doble de km, 9 % menos), −0,09 en Amarok y Hilux, −0,055 en 208.

### 3.2 Cómo se ajusta

Sobre el pool del modelo (§4.1), con medianas, sin librerías nuevas (el worker no tiene numpy):

1. `A0[año]` = mediana de `ln(precio)` de los años con `min_year_n` (8) avisos o más.
2. Recorte: fuera los avisos con precio menor a 0,45 o mayor a 2,2 veces `exp(A0[año])`.
3. `G[versión]` = mediana de `ln(precio) − A0[año]`, para las versiones con `min_trim_n` (15) avisos o más.
4. `A[año]` = mediana de `ln(precio) − G`: el nivel del año sin el efecto de qué versiones se venden ese año.
5. `H[caja]` = mediana del residuo, para las cajas con 15 avisos o más.
6. `B` = pendiente del residuo contra `ln(km) − KM[año]`, con los avisos de 5.000 a 400.000 km; recortada a [−0,35, 0].
7. Se repiten 3 a 6 hasta que ningún coeficiente cambie más de 0,5 % (máximo 4 pasadas).
8. Se guardan los cuartiles del residuo final (`q25`, `q75`): dan el rango «barato / caro» que hoy dan `p25` y `p75`.

Es lo que corre el anexo (A), con una sola pasada.

### 3.3 El valor de un aviso

`fair_value(aviso, curva)` devuelve `None` si el modelo no tiene curva o su año no tiene `A`. Si no:

- `value` = `exp(ln(valor))`; `p25` = `value · exp(q25)`; `p75` = `value · exp(q75)`.
- `n` = avisos de ese año en el ajuste. Es el `n` que leen los pisos de hoy (5 para tener referencia, 10 para 🔥 en f3).
- `level` = `curve` si la versión del aviso tiene prima; `curve_noversion` si no. Sin versión, el valor es el de la versión típica: vale lo mismo que el nivel `model` de hoy.
- `known` = qué datos entraron: versión, caja, km.
- `d` = % debajo del valor: `(1 − precio_usd / value) · 100`.

### 3.4 Regla híbrida

Para cada aviso, la referencia que se usaría en real:

1. Si la referencia de hoy es de gemelos (`level_used = trim_transmission`, `n ≥ min_n`): **se queda la de hoy**.
2. Si no, y el modelo tiene curva habilitada (§3.5) y `fair_value` devuelve un valor: **el valor justo**.
3. Si no: la de hoy.

«No tener referencia hoy» incluye a los avisos que el scorer no fue a buscar (`prepare(refs_limit=…)`): para esos el valor justo sale gratis, porque no necesita una consulta por aviso. En la sombra se marcan aparte (`ref.fetched = false`) y no entran en las comparaciones.

Por qué híbrida y no «siempre valor justo»: con gemelos, las dos empatan y a veces ganan los gemelos.

| modelo | referencia de hoy | autos | error hoy | error valor justo | errores > 20 % hoy → valor justo |
|---|---|---|---|---|---|
| Hilux | gemelos | 109 | 6,1 % | 5,8 % | 8,3 % → 9,2 % |
| Hilux | versiones mezcladas, misma caja | 28 | 13,8 % | 7,2 % | 32,1 % → 21,4 % |
| Hilux | todo el modelo | 43 | 10,7 % | 6,7 % | 18,6 % → 2,3 % |
| Amarok | gemelos | 106 | 6,0 % | 6,9 % | 6,6 % → 8,5 % |
| Amarok | versiones mezcladas, misma caja | 37 | 7,0 % | 6,2 % | 8,1 % → 10,8 % |
| Amarok | todo el modelo | 37 | 16,5 % | 8,0 % | 40,5 % → 13,5 % |
| Gol Trend | gemelos | 190 | 7,2 % | 6,6 % | 6,3 % → 6,3 % |
| Gol Trend | versiones mezcladas, misma caja | 76 | 6,8 % | 6,0 % | 7,9 % → 6,6 % |
| Gol Trend | todo el modelo | 48 | 7,4 % | 6,7 % | 8,3 % → 8,3 % |

- Error = mediana de `|ln(precio / referencia)|`, sobre avisos que el ajuste no vio (1 de cada 5).
- Hilux y Amarok: contra `comparables()` llamada ese día. Gol Trend: contra el `price_ref` guardado en sus matches.
- En Hilux, de 41 «baratos» de hoy (10 % o más debajo), 14 dejan de serlo con el valor justo y aparecen 5 nuevos. En Amarok, 5 de 35 y 6 nuevos.

### 3.5 Habilitación por modelo

Con pocos avisos el valor justo puede ser peor que la referencia de hoy. Probado con la mitad de los avisos (108 a 171 de entrenamiento), sin gemelos: Captur 6,9 % → 5,7 %, Strada 6,6 % → 5,6 %, **Fit 9,3 % → 10,3 %** (peor).

Por eso cada corrida del job mide cada modelo y decide sola. Los dos errores se miden sobre la misma muestra de hasta 300 avisos del modelo (`cohort_sample`):

- `cv_err`: error del valor justo en 5 tandas (`id % 5`): cada aviso se predice con una curva ajustada sin su tanda.
- `cohort_err`: error de la referencia «todo el modelo» de hoy, con sus mismas reglas: la mediana de los avisos del pool con año ±`year_tol` y km ±`km_tol_pct` (un comparable sin km entra), sin el propio aviso ni sus reposts, y con el piso `floor_of_p75`.
- La curva queda **habilitada** si el modelo tiene `min_listings` (150) avisos o más y `cv_err ≤ cohort_err`.
- Una curva ya habilitada se deshabilita recién cuando `cv_err > 1,05 × cohort_err`. Sin ese margen, un modelo parejo cambiaría de referencia de un día para el otro y sus scores saltarían.

Los modelos con 150 avisos o más son 90 y juntan el 98,6 % de los matches.

### 3.6 Lo que no ve

- **Tracción y cabina en pickups.** Con la misma versión y año, una 4x4 vale 4,5 a 8 % más que una 4x2 (Amarok +3,5 / −4,3; Hilux +2,3 / −3,3; Ranger +2,8 / −1,7). El título lo dice en el 75 a 90 % de los avisos. No entra en la primera versión: el informe mide cuánto error deja, para decidir si se suma.
- **Motor** (1.2 contra 1.6), cuando no está en la versión.
- **Carrocería**, en los modelos que tienen más de una (Kangoo furgón y de pasajeros). `listings.body_type` existe; se suma como un factor más si el informe muestra que hace falta.
- **El estado del auto.** Sigue sin verse.
- **Prima de versión que cambia con la generación.** La fórmula usa una prima por versión para todos los años. El informe la mide por tramo de años.
- **Avisos sin versión** (23 %): valen como la versión típica. Si son base, siguen pareciendo baratos, como hoy.
- **El propio aviso está en el ajuste.** Con 8 avisos o más por año mueve poco la mediana; no se corrige.

## 4. Dónde vive

### 4.1 El pool: `public.price_pool(p_make, p_model)`

Función SQL STABLE nueva. Devuelve los avisos de un modelo que hoy pueden ser comparables de alguien: las reglas de `comparable_listings()` que no dependen del aviso que se compara.

| regla de `comparable_listings()` | en `price_pool` |
|---|---|
| misma marca y modelo (`lower()` de los dos lados) | sí: son los argumentos |
| `source <> 'directo'` (el precio de una agencia propia no es mercado) | sí |
| `price_usd > 0`, sin `price_partial`, visto en los últimos `max_age_days` | sí |
| activo, o desaparecido hace menos de `gone_max_age_days` (sin límite si la clave falta) | sí |
| no «sin confirmar» (`confirm_sources` + `listing_unconfirmed`) | sí |
| un repost cuenta solo mientras su original no cuenta | sí |
| no es el propio aviso; no es un repost del propio aviso | no: son del aviso |
| ventana de año; sin filtro si el aviso no tiene año | no: es del aviso |
| ventana de km; un comparable sin km pasa; sin filtro si el aviso no tiene km | no: es del aviso |

- Devuelve `id`, `probable_repost_of`, `year`, `trim`, `transmission`, `mileage_km`, `price_usd`: lo que necesitan el ajuste y `cohort_err`.
- Las piezas no se confunden con autos: `mark_not_vehicle` les pone `price_partial`.
- `comparable_listings()` y `comparables()` **no se tocan**.
- Un test pgTAP fija la equivalencia: para un aviso, `price_pool` filtrado con las cuatro reglas del aviso devuelve los mismos ids que `comparable_listings`, incluidos los casos sin año y sin km.
- Permisos: `revoke execute … from public, anon, authenticated` y `grant … to service_role`, como `comparables()`. Supabase lo da a todos por defecto.
- El piso de precio de `comparables()` no se copia al ajuste: el ajuste usa su propio recorte (paso 2 de §3.2).

Para saber qué modelos ajustar, el job hace una consulta barata (avisos con precio, vistos en `max_age_days`, sin `directo`, agrupados por marca y modelo, con `min_listings` o más) y después pide `price_pool` de a un modelo. El `n` que vale es el de las filas devueltas.

### 4.2 Las tablas

Solo el worker las lee y las escribe: RLS sin políticas y permisos revocados, como `match_decisions`.

`public.model_price_curves`, una fila por modelo, que cada corrida pisa:

| columna | contenido |
|---|---|
| `make`, `model` | en minúsculas, clave primaria |
| `curve jsonb` | `years` {año: {a, n, km}}, `trims` {versión: {g, n}}, `transmissions`, `km_slope`, `resid` {q25, q75} |
| `n`, `cv_err`, `cohort_err`, `enabled` | §3.5 |
| `params_hash`, `fitted_at`, `run_id` | con qué parámetros y en qué corrida |

`public.fair_value_runs`, una fila por corrida, como `market_stats_runs` y `seller_classification_runs`:

| columna | contenido |
|---|---|
| `started_at`, `finished_at`, `status`, `trigger` | `schedule`, `catchup` o `cli` |
| `params jsonb`, `params_hash` | `app_config.fair_value` de esa corrida |
| `models_seen`, `models_fitted`, `models_enabled`, `error` | |
| `stats jsonb` | por modelo: `n`, `cv_err`, `cohort_err`, `enabled`, `km_slope`, los `a` por año y `guard_flips` (§7) |

Las corridas son el historial: de ahí sale la estabilidad día a día (criterio 4). Unos 30 KB por corrida; el job borra las de más de 90 días.

### 4.3 El job

- `worker/intelligence/fair_value.py`: puro. `fit(rows, params) → Curve | None`, `evaluate(curve, rows, params)` (§3.5), `fair_value(listing, curve)`, `rule_h(ref, fetched, value)`, `shadow(...)` (§5).
- `worker/db/repos/price_curves.py`: listar modelos, leer el pool, guardar curvas y corridas, cargar curvas.
- `worker/pipeline/fair_value.py`: `fit_all()` y `fair_value_loop(stop)`, registrado en `main.py`.
- `worker/tools/fair_value.py --dry-run [--model "Toyota Hilux"]`: ajusta y muestra sin escribir.

**Horario.** Loop propio, calcado de `market_stats_loop`, no dentro de `nightly_loop`:

- Corre a `schedule.hour` (03:30 ART, antes del rescore de las 04:00).
- **Recupera:** al arrancar y en cada vuelta, si la última corrida `ok` tiene más de 26 h, corre (`trigger = catchup`). Un reinicio del worker con una corrida fresca no ajusta de nuevo.
- No va en `nightly_loop` porque ese loop corre sus pasos también en cada arranque y no recupera un horario perdido; además demoraría el rescore y la retención, que van en la misma tarea.

**Lo que tiene que respetar:**

- Leer `mode` antes de cualquier SQL: el worker se despliega antes que las migraciones. Con `off` no consulta ni la tabla.
- No retener una conexión del pool mientras calcula (el pool tiene 5): leer las filas, soltar, ajustar, volver a tomar para escribir.
- El ajuste es CPU pura: va en `asyncio.to_thread`, como `market_stats`. Si no, frena el loop y el heartbeat se corta a los 900 s.
- Un fallo se registra con `log_error("fair_value", …)` y cierra la corrida con `status = failed`. Las curvas anteriores quedan.

### 4.4 El scorer

- **Carga de curvas.** `Scorer.create()` corre en cada tanda de crawl, rescore y rematch. Las curvas habilitadas se guardan en una caché del proceso (`pipeline/fair_value.py`), que se recarga cuando pasan 10 minutos. Solo con `mode` en `shadow` o `live`.
- **Dónde se calcula.** En `Scorer.evaluate`, después de `engine.evaluate` y del margen, igual que `margin_ref`. `Evaluation` suma el campo `shadow_fair_value` y `Evaluation.row()` lo pone en `score_breakdown`. Hace falta la línea en `row()`: arma el breakdown de cero.
- **Todas las escrituras de matches pasan por ahí** (crawl, rematch, rescore, enrich).
- `tools/explain_match.py` llama a `engine.assess` directo: se le agrega el bloque del valor justo, para poder mirar un caso.
- **Nunca lanza y siempre es JSON válido.** `shadow_fair_value` viaja en el mismo JSON con el que se escribe la fila de f2: un NaN, un infinito, un `Decimal` o una fecha harían fallar la escritura de toda la tanda de esa búsqueda, y en el crawl se perdería la alerta. Solo floats finitos redondeados, enteros, booleanos y textos, como `f3._r`. Cualquier excepción se registra con `warn_limited` y la evaluación sigue sin el bloque.
- f2 sigue decidiendo todo con la referencia de hoy.

## 5. Modo sombra: qué se guarda

En `matches.score_breakdown.shadow_fair_value`, al lado de `shadow_f3`. Sin cambio de esquema en `matches`.

```json
{"v": "fv1", "params": "3f9a1c2b7d10", "fitted_at": "2026-11-21T06:31:02Z",
 "value": 10345.0, "p25": 9620.0, "p75": 11010.0, "n": 121, "level": "curve",
 "known": {"trim": true, "transmission": false, "km": true},
 "d": 12.3,
 "ref": {"fetched": true, "d": 9.8, "level_used": "model", "n": 350},
 "rule_h": true,
 "f2": {"score": 78, "level": "good", "guard": null, "excluded": false},
 "f3": {"score": 74, "level": "good"},
 "budget": {"usd": 8000, "value_ratio": 1.12, "price_ratio": 0.93}}
```

- Se guarda para todo match cuyo aviso tiene valor justo, también cuando hay gemelos: así el informe compara en todos lados.
- `params`: hash de `app_config.fair_value` sin `mode`. Si un parámetro cambia, la medición empieza de nuevo ese día.
- `ref`: la referencia de hoy. `d` es el `diff_pct` del `price_ref`, que viene lleno aunque `n` no llegue a `min_n`; el informe aplica el piso.
- `rule_h`: si la regla híbrida usaría el valor justo para este aviso.
- `f2` y `f3`: el score y el nivel que darían con esa referencia. Solo cuando `rule_h` es verdadero.
  - Se calculan con las mismas funciones puras (`scoring.score`, `f3.assess_f3`) y un `PriceRef` **nuevo**, con su propio `diff_pct`. Un `replace()` del de hoy puntuaría el descuento de hoy: `diff_pct` le gana a la mediana.
  - `median_km` va vacío: el valor ya ajusta por km, y el componente km de f2 queda neutro (0,5) para no contarlo dos veces.
  - Para f3, `curve_noversion` se pasa como `level_used = "model"`: recibe la misma baja de confiabilidad sin tocar `f3.py`.
  - `f2.excluded` y `f2.guard` se guardan: `score()` devuelve un número aunque excluya. En f3 el nivel puede ser `excluded`.
  - `assess_f3` lanza con datos mal formados: va en su propio `try`.
- `budget`: solo en búsquedas con `price_max` y con cotización (`Scorer.fx_rate`). `value_ratio` = valor del auto / tope; `price_ratio` = precio / tope. Las monedas se convierten con `matching.filter_currency` y `matching.price_in`, las mismas del filtro de precio.
- No hay bump de `SCORING_VERSION`: el rescore periódico lo va llenando en los matches de avisos activos de los últimos `rescore.days`.
- La sombra de f3 no se reinicia: nada de lo que f3 lee cambia.

**La bitácora de decisiones.** `decision_log.f2_fields` guarda `score_breakdown` sin `shadow_f3`, así que `shadow_fair_value` queda dentro de `match_decisions.f2_breakdown` con lo que se sabía al decidir, sin columnas nuevas. Dos límites:

- La bitácora solo escribe mientras `score_model_f3.mode` es `shadow` o `live` (`record_card` no hace nada si ninguna evaluación trae `shadow_f3`). Si f3 se apaga, la sombra del valor justo se queda sin bitácora.
- Son pocas filas: unas 270 decisiones de tarjeta por día (3.730 en los últimos 14). Las filas de tarjeta son de antes del detalle, muchas sin versión ni caja.

**Quién puede leerlo.** El dueño de la búsqueda puede leer `score_breakdown` de sus matches por la API, como hoy lee `shadow_f3` y `price_ref`. El bloque no tiene nada reservado a un plan.

**Lo que la sombra no ve.** Un aviso que hoy se excluye por «anticipo» (65 % o más debajo de su referencia) no tiene match, así que tampoco tiene sombra. El job cuenta, por modelo, cuántos avisos del pool cruzan ese 65 % con una referencia y no con la otra (`guard_flips`). Es aproximado: usa la referencia «todo el modelo».

## 6. El presupuesto en contexto: medición

### 6.1 Lo que se sabe hoy

Sumando todas las búsquedas con tope, los autos cercanos al tope parecen abrirse 7,5 veces más (0,6 % contra 4,5 %). Es un efecto del tamaño de las listas: cada persona abre uno o dos autos por búsqueda; las de tope holgado traen 102 autos y las de tope ajustado, 40.

Comparando dentro de la misma búsqueda y la misma banda de score (anexo B), 1 = sin preferencia:

| señal | tramos | aperturas contra lo esperado |
|---|---|---|
| precio contra el tope | < 50 % · 50–70 · 70–85 · 85–100 | 0,72 · 0,97 · 0,99 · 1,03 |
| valor del auto contra el tope | < 60 % · 60–80 · 80–95 · 95–110 · > 110 | 0,54 · 0,98 · 0,99 · 1,01 · 1,08 |
| año | viejo · medio · nuevo | 1,05 · 0,93 · 1,02 |
| km | pocos · medio · muchos | 1,02 · 0,89 · 1,10 |
| precio | barato · medio · caro | 1,10 · 0,93 · 0,87 |

- El único tramo que se aparta es «vale menos del 60 % del tope»: 5 aperturas contra 9 esperadas. Son muy pocos casos.
- Lo que manda es la posición: los 5 primeros puestos por score se abren 8,0 %; del 51 en adelante, 0,18 %. El 65 % de las aperturas cae en los primeros 20.
- Los clics no pueden decir cómo pesar año, versión o presupuesto: la gente abre lo que el score pone arriba.

### 6.2 Lo que se mide en la sombra

- `budget.value_ratio` y `price_ratio` quedan guardados con cada match (§5).
- El informe (§7) repite la tabla de arriba cada semana, con el valor justo en lugar de la mediana de hoy.
- No hay criterio de aprobación: es dato para decidir la prueba de §6.4.

### 6.3 Registrar la posición (PR aparte, opcional)

Hoy `listing_detail_viewed` guarda el aviso y si vino de una alerta o de la web. No guarda en qué puesto estaba ni con qué orden. Sin eso no se puede separar «lo abrió porque estaba arriba» de «lo abrió porque lo prefería».

- **El link.** `ListingCard` recibe un prop opcional con la búsqueda, el orden y el puesto, y los agrega al link: `?src=796&ord=score&pos=3`. La tarjeta se comparte con `/app` y `/app/saved`, que no lo pasan. En la página de resultados `s` ya es el orden y `p` la página: por eso los nombres nuevos.
- **El evento.** `markSeen` suma `profile_id`, `sort` y `position` a `listing_detail_viewed`. `src` se valida contra las búsquedas del usuario que tienen ese aviso.
- **Las impresiones.** Evento nuevo `search_results_viewed`: `profile_id`, `sort`, `filter`, `page` y los ids de esa página. «Ver más» vuelve a pintar todo desde el primero: se mandan solo los 50 nuevos. Lo dispara un componente cliente con clave (búsqueda, orden, filtro, página), como `VisibleResultsReport`, porque la página se repinta sola mientras una búsqueda se prepara.
- **Efecto en las métricas.** Cualquier evento cuenta como actividad en `v_validation_criteria` (criterio 4), en `last_activity_at` y en los días activos de `/admin`. Para que mirar una lista no vuelva «activo» a nadie, el evento nuevo se excluye de esos tres. Eso sí pide una migración chica.
- Dos tests e2e buscan el link de la tarjeta por su `href` exacto (`acceptance.spec.ts`, `price-tracks.spec.ts`).
- Solo `web/`, más esa migración. Next 16: leer `node_modules/next/dist/docs` antes, como pide `web/AGENTS.md`.

### 6.4 La prueba de orden (después, con otro OK)

No se prende con este diseño. Queda definida para no improvisarla:

- **Quién:** la mitad de las cuentas, por interruptor (`app_config.budget_order`, como `landing_hero`).
- **Qué cambia:** solo el orden «Mejor oportunidad» de la lista y el orden del resumen diario, en búsquedas con tope. Clave de orden = score + un ajuste de −6 (el auto vale 60 % del tope o menos) a +4 (vale 105 % o más). Niveles y alertas quedan iguales.
- **Qué se mide:** clics al aviso original y aperturas por búsqueda activa.
- **Cuánto tarda:** las búsquedas con tope juntan 450 aperturas y 126 clics al aviso desde que existe el producto, casi todo en el último mes. A ese ritmo, entre 1 y 3 meses para ver una diferencia de 25 %. Es una estimación gruesa.
- **Necesita:** el valor justo calculándose (este diseño) y la posición registrada (§6.3).

## 7. Informe y criterios para pasar a real

`worker/tools/fair_value_report.py`: solo lectura, una transacción READ ONLY, markdown en castellano, como `shadow_report.py`.

De dónde lee cada cosa:

| qué | de dónde |
|---|---|
| cobertura y sesgos (criterios 1 a 3) | `matches`: el estado de hoy de todos los matches re-puntuados |
| estabilidad (criterio 4) y `guard_flips` | `fair_value_runs.stats` |
| decisiones (criterios 5 y 6) | `match_decisions`: lo que se sabía al decidir. Por cada match, la fila que decide (`f3_decides`): la de tarjeta, o la del detalle si la tarjeta esperaba |
| modelos habilitados y sus errores | `model_price_curves` |
| presupuesto (§6.2) | `matches` y `events` |

La decisión alternativa (alerta sí o no, con el nivel y el score de `f2` bajo la regla híbrida) se calcula en el informe con `notifications.engine.classify` y la `audience` guardada, igual que hace f3.

**Criterios, fijados antes de medir.** Se evalúan con 14 días de sombra o más, con un solo `params`.

| # | criterio | umbral |
|---|---|---|
| 1 | Cobertura: de los matches sin gemelos, cuántos reciben valor justo | 80 % o más |
| 2 | Sesgo de versión: correlación entre `d` y la prima de versión, en los matches con `rule_h` | entre −0,10 y 0,10 (hoy −0,44 y −0,18) |
| 3 | Sesgo de km: correlación entre `d` y el km relativo al de su año, en los mismos | entre −0,10 y 0,10 (hoy −0,40 en Gol Trend) |
| 4 | Estabilidad: cambio mediano de `A[año]` entre corridas de días seguidos, en los modelos con 400 avisos o más | 1,5 % o menos |
| 5 | Volumen: alertas con la regla híbrida contra alertas de hoy | entre 0,85 y 1,10 |
| 6 | Revisión de Juan: 20 alertas que se caerían y 20 que aparecerían, al azar | el criterio nuevo acierta en 14 o más de cada grupo |

Si falla uno, no se pasa a real: se ajusta el parámetro que corresponda y la medición empieza de nuevo ese día.

## 8. Paso a real (otro PR, con otro OK)

No es parte de este diseño. Lo que tocaría:

- `matches.price_ref` pasa a salir de la regla híbrida. `level_used` suma `curve` y `curve_noversion`. Nada lo valida hoy, pero la web decide por sus tres valores en la ficha (`listings/[id]/page.tsx`), el inspector de `/admin`, `lib/copy.ts` y `lib/margin-view.ts`.
- Textos: «X % debajo de N comparables» no describe un valor justo. Hay que escribir la frase nueva (por ejemplo, «X % debajo de lo que vale un 2017 Trendline con 90.000 km, según N avisos del modelo») en el mail, la ficha y el bot.
- Todo lo que lee el descuento cambia con él: las banderas de riesgo, el umbral de Pro (`diff_pct` del aviso) y `expired_search_matches.diff_pct`.
- La lista de comparables de la ficha (`comparable_pool`) sigue mostrando avisos parecidos.
- El margen de Pro (PRO-02) sigue con la mediana de agencias de los gemelos: el valor justo no separa por vendedor.
- `f3.reliability` aprende `curve_noversion`.
- Bump de `SCORING_VERSION` y rescore completo. Rollback: `fair_value.mode = shadow` y otro rescore.
- Más adelante, el panel de agencias (`dealer_market_ref`) puede leer el mismo valor, para que «lo que vale un auto» tenga una sola definición.

## 9. Configuración

`app_config.fair_value`. Solo en la migración, como `score_model_f3`: `seed.sql` corre después con `on conflict do nothing` y no agrega nada.

```json
{"mode": "shadow", "min_listings": 150, "min_year_n": 8, "min_trim_n": 15,
 "price_trim": {"low": 0.45, "high": 2.2}, "km_range": {"min": 5000, "max": 400000},
 "km_slope_min": -0.35, "max_passes": 4, "cohort_sample": 300,
 "disable_margin": 1.05, "schedule": {"hour": "03:30"}}
```

| clave | límites |
|---|---|
| `mode` | `off`, `shadow`, `live`. `live` se acepta y, hasta el PR de paso a real, se comporta como `shadow` |
| `min_listings` | entero, 50 a 5.000 |
| `min_year_n`, `min_trim_n` | enteros, 5 a 200 |
| `price_trim.low` · `high` | 0,2 a 0,9 · 1,2 a 5 |
| `km_range.min` · `max` | enteros, 0 a 50.000 · 100.000 a 1.000.000 |
| `km_slope_min` | −1 a 0 |
| `max_passes` | entero, 1 a 10 |
| `cohort_sample` | entero, 50 a 2.000 |
| `disable_margin` | 1 a 1,5 |
| `schedule.hour` | `HH:MM` |

Dónde se registra, igual que `score_model_f3`:

1. La migración: un solo literal JSON, `on conflict (key) do nothing`.
2. `worker/intelligence/config.py`: defaults (con `mode: off`, para que una base sin migrar se comporte como hoy), límites y normalizador. Un valor fuera de rango cae a su default, clave por clave. `intelligence/fair_value.py` recibe los parámetros ya normalizados: no lee config.
3. `web/lib/admin-config.ts`: función de validación, su rama en `validateConfigChange` y las etiquetas. Sin eso `/admin/config` guarda cualquier objeto y el worker cae a los defaults sin avisar.
4. `web/app/admin/config/page.tsx`: la ayuda de la clave.

Rollback sin deploy: `mode = off`. Las tablas y lo guardado quedan.

## 10. Tests

- `test_fair_value.py` (puro): el ajuste recupera coeficientes conocidos de datos sintéticos; recorte de precios absurdos; versión con pocos avisos sin prima; año con pocos avisos sin valor; `B` positivo recortado a 0; sin km, sin caja, sin versión; `evaluate` deshabilita una curva peor que la referencia y respeta el margen de 1,05; `rule_h` en sus ramas, incluida la referencia no buscada; `fit` con cero filas.
- **JSON válido:** `shadow()` con precios en `Decimal`, NaN, infinito y fechas devuelve un bloque que `json.dumps(allow_nan=False)` acepta, o ninguno.
- `test_fair_value_postgres.py`: guardar y cargar curvas y corridas; `fit_all` no consulta nada con `mode = off`; la recuperación corre con una corrida vieja y no con una fresca.
- `test_fair_value_shadow_engine.py`: con `mode = off` la fila del match es idéntica a la de hoy; con `shadow`, score, nivel y `price_ref` de f2 no cambian y aparece `shadow_fair_value`; un fallo del valor justo no rompe la evaluación; `excluded` y `guard` viajan.
- `test_decision_log.py`: `shadow_fair_value` viaja en `f2_breakdown`.
- `test_fair_value_config.py` y `test_fair_value_migration_defaults.py`: normalizador y límites; el JSON de la migración contra los defaults del código, como hace f3.
- pgTAP `fair_value_test.sql`: RLS y permisos de las dos tablas; equivalencia de `price_pool` (§4.1); que `anon` y `authenticated` no puedan ejecutarla; la clave de config.
- Web: `admin-config.test.ts` para el validador; `score-breakdown.test.ts` y `copy.test.ts` hoy fijan que `shadow_f3` no se muestra por su nombre: se suma `shadow_fair_value` a los dos. La ficha y el inspector leen por lista de componentes, así que una clave nueva no se pinta.

## 11. Riesgos y lo que no sabemos

- **Las pruebas son de un día.** Tres modelos grandes y tres medianos, con el pool del 20/11. La sombra es la medición de verdad.
- **Predecir mejor el precio publicado no es lo mismo que detectar mejor una oportunidad.** Es la mejor medida disponible; el criterio 6 pone el ojo de Juan.
- **El pool es nacional y mezcla fuentes y monedas.** Igual que hoy. El valor justo no lo arregla.
- **Versiones mal leídas.** La prima se calcula sobre `listings.trim`: si el título se leyó mal, la prima es de otra versión. Mismo dato que usan los gemelos hoy.
- **Depende de la sombra de f3 para la bitácora** (§5). Los criterios 1 a 4 no; los 5 y 6 sí.
- **Tamaño.** `shadow_fair_value` suma unos 350 bytes a cada match re-puntuado y a cada fila nueva de `match_decisions`.
- **Dos sombras a la vez.** f3 está en sombra desde el 09/11. El paso a real del valor justo conviene decidirlo después del de f3, para no mover dos cosas juntas.
- **Tres referencias de precio.** Gemelos, valor justo y la del panel de agencias, cada una con sus reglas. Este diseño no las unifica (§8).

## 12. Decisiones para Juan

1. **Aprobar el valor justo en sombra.** No cambia nada visible. Recomendado: sí.
2. **Regla híbrida** (gemelos cuando hay, valor justo cuando no) **o siempre valor justo.** Recomendado: híbrida; la tabla de §3.4 muestra que con gemelos no hay nada que ganar.
3. **Registrar la posición en la lista** (§6.3). Recomendado: sí; sin eso ninguna medición de preferencias es confiable.
4. **Tracción de las pickups** en la primera versión o después de medir. Recomendado: después.

## 13. Ejecución

Con el diseño aprobado, dos sesiones independientes, las dos desde `origin/main`:

| sesión | alcance | termina en |
|---|---|---|
| A | migración, `intelligence/fair_value.py`, config, repo, job, scorer, `explain_match`, informe, tests, validador de `/admin/config` | un PR |
| B | posición e impresiones en la lista (§6.3): `web/` y su migración chica | un PR |

- La migración de A lleva una versión posterior a `20270106120000`.
- **A se mergea y se aplica junto:** con una migración sin aplicar en producción, el bot de reparación frena sus deploys. Aplicarla pide el OK de Juan.
- Después: 14 días de sombra, informe, y la decisión de pasar a real.
