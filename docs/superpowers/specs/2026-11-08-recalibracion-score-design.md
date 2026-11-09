# Recalibración del Opportunity Score · «precio × encaje» (f3)

Fecha: 2026-11-08. Estado: **borrador para que Juan lo apruebe**. No hay nada implementado ni ninguna migración escrita. No se tocó producción: todo lo de este documento se midió con SELECT de solo lectura, y las únicas funciones llamadas fueron las STABLE `plan_limits_for` y `search_access_active`.

Pedido de Juan: «tenemos que recalibrar el score; es clave para todo el resto de las búsquedas». Cada afirmación se mide **búsqueda por búsqueda, sobre las búsquedas actuales**.

**Cómo se llegó a esta versión:**
- Cuatro candidatas (A, B, C y D) se midieron contra la fórmula de hoy. De ahí salió **F**, el ángulo C de dos ejes con los injertos que pidieron los jueces.
- Una verificación adversarial de F encontró cinco defectos medibles: un escalón de encaje, alertas creíbles perdidas en el conjunto extendido, basura dentro de las 🔥 «creíbles», el ejemplo del PRD frágil y la concentración de 🔥.
- **F2**, la versión de este documento, corrige los cinco. Después pasó dos verificaciones más: una de números, que volvió a correr todo desde cero, y otra de diseño contra el código.
- Este spec es F2 con las correcciones de esas dos verificaciones (§16).

**Cómo se midió:**
- Con el backtest de solo lectura del score: una fila por match, con los datos que había en la tarjeta y en el detalle.
- Hoy (`cur@card`, la fórmula actual con los datos de la tarjeta, que es la que decide las alertas), F (`F@dec`) y F2 (`F2@dec`) corrieron **en la misma consulta**.
- **Conjunto actual:** las 79 búsquedas con acceso activo a las 21:38 UTC, con 3.196 matches y 256 frescos.
- **Conjunto extendido:** suma las búsquedas deshabilitadas o vencidas que tuvieron un match en 30 días. Son 269 búsquedas con matches, 13.817 matches y 1.882 frescos.
- Para no pasar el límite de 60 s, cada conjunto corrió en partes por `search_id`, y las partes se sumaron.

**Anexos:**
- [`2026-11-08-recalibracion-score-por-busqueda.md`](2026-11-08-recalibracion-score-por-busqueda.md): todas las búsquedas actuales, una por una, y el usuario que pagó, aviso por aviso.
- [`2026-11-08-recalibracion-score-f2.sql`](2026-11-08-recalibracion-score-f2.sql): la CTE del backtest con la que se midió F2.

## Resumen

- **Qué significa 🔥.** Un precio creíble por debajo del mercado en un auto que encaja con lo que pidió la persona, sin nada sobre el precio que haya que verificar. El score se arma con dos ejes, **Precio** (qué tan barato y qué tan creíble) y **Encaje** (cuánto cumple lo pedido), y 🔥 pide los dos juntos.
- **Datos que faltan.** Un dato faltante no decide el nivel, solo ordena dentro de él. El precio ideal se gradúa dentro del presupuesto. La antigüedad sale del score, así que el nivel guardado ya no decae.
- **Datos que no son lo que dicen:**
  - un precio de relleno (USD 11.111) cuenta como sin precio;
  - un vendedor confirmado distinto del pedido, incluido un «particular» que escribe como agencia, deja el aviso como mucho en «coincidencia»;
  - un aviso de Facebook marcado «Sold ·» pasa a terminado en el colector.
- **En las búsquedas actuales** (hoy → F2):
  - alertas 111 → 103; alertas 🔥 32 → 22;
  - 0 alertas a «buena» o más sin año, sin precio o con sospecha de anticipo (hoy 14 distintas);
  - 🔥 en la lista 132 → 356, y 355 de ellas son ofertas creíbles (hoy 76);
  - ninguna búsqueda pierde una alerta que era creíble al decidir.
- **En el conjunto extendido** (269 búsquedas):
  - alertas 868 → 831, y las malas a «buena» o más pasan de 73 a 0;
  - las alertas creíbles perdidas al decidir pasan de 19 en 3 búsquedas (con F) a 0.
- **El usuario que pagó:**
  - el Gol recibe al decidir el auto que se perdió (409916);
  - la Clio recibe lo mismo que hoy;
  - la Corsa sigue sin alertas, porque su única candidata (264835) tiene voz de agencia en la descripción;
  - su 2007 descartado sigue 🔥 arriba del 2011 que guardó.
- **Lo que cuesta o queda abierto:**
  - Hay que tocar código: ~300 líneas y ~40 tests sobre lo que ya pedía F, más un bump de versión.
  - La pestaña «Oportunidades» crece de 132 🔥 a 356, casi todas de backfill.
  - El criterio 6 de la sombra (ninguna búsqueda con más de 40 % de 🔥) no se cumple, y la causa es el pool de comparables, no la fórmula.
  - Revisa decisiones que Juan ya tomó: PAR-02 tramo 1, PRO-01, DESCRIPTION_INTELLIGENCE y el umbral Pro del 14/10. Están marcadas con ⚠️ en §14.
- **Próximo paso:** dos semanas en modo sombra con criterios fijados de antemano, sin cambiar ninguna alerta ni ningún score visible. El arreglo de «Sold ·» puede salir ya, aparte.

## 1. Problema, medido en las búsquedas actuales

Cifras de hoy · tarjeta. Salvo donde se indica, salen de la corrida de las 21:38 (79 búsquedas).

| hecho | hoy |
|---|---|
| 🔥 que no son creíbles: menos de 10 comparables, más de 35 % debajo, sin año o con sospecha de anticipo | 56 de 132 (42 %) |
| 🔥 a más de 35 % debajo de la mediana | 14 |
| alertas a «buena» o más sin año / con `partial_price_suspect` / sin precio | 11 / 9 / 3 (14 alertas distintas) |
| lo mismo en el conjunto extendido | 73 alertas |
| búsquedas con matches frescos y cero alertas | 14 de 42 |
| búsquedas con 6 o más filtros+preferencias que llegan a 🔥 | 0 de 12 (con 8 o más: 0 de 6) |
| correlación entre cantidad de filtros+preferencias y score medio de la búsqueda | −0,315 |
| decisión de alerta distinta entre tarjeta y detalle · nivel distinto (frescos; corrida de las 20:02) | 7 · 24 de 244 |
| 🔥 guardadas (el nivel decae cada 6 h) contra 🔥 al decidir (corrida de las 22:55) | 39 contra 130 |
| conteo «por debajo de comparables» de los mails (= 🔥 guardadas) | 39 matches en 15 búsquedas; las ofertas creíbles vivas y sin duplicados son 589 en 47 |
| usuario que pagó (Gol 92, Clio 95, Corsa 97) | 0 🔥 y 0 alertas de Gol y Corsa. El mail le dijo «0 por debajo» con 7 Gol a 21–45 % debajo |

Las causas están verificadas contra el código:
1. **El precio satura a 10 % debajo.** Un aviso a 64 % debajo vale lo mismo que uno a 10 %, así que lo sospechoso queda arriba.
2. **Una preferencia desconocida cuenta como fallida** (−12,5 puntos con 2 preferencias). Cada filtro desconocido resta 3,75. Por eso la tarjeta de FB del usuario que pagó no podía pasar de 66.
3. **`price_target` cuenta el precio dos veces** y castiga autos dentro del propio presupuesto del usuario.
4. **La antigüedad decae el nivel guardado.** La pestaña, el dashboard y los mails leen un nivel que ya no es el de la alerta.
5. **Se decide con la tarjeta,** antes de leer el detalle, y un re-score nunca alerta.
6. **km y completitud casi no se mueven:** el km nunca pasa de 0,75 y la completitud no predice nada (AUC 0,48–0,51).

**Lo que F (la propuesta anterior) no arreglaba,** medido en su verificación:
- **Un escalón de encaje.** En la 253, una tarjeta de ML sin caja ni combustible quedaba con encaje 0,44, apenas debajo del corte de 0,45. 17 alertas creíbles caían a «coincidencia».
- **Pérdidas en el extendido.** 7 búsquedas perdían 26 alertas creíbles, y las alertas 🔥 caían a 0,57 de las de hoy.
- **Basura dentro de las 🔥 «creíbles».** Entre los 383 avisos que F alertaba o ponía en 🔥 había 5 a USD 11.111 del mismo vendedor de FB, 7 con título «Sold ·» y 14 «particulares» con texto de agencia.
- **El ejemplo del PRD** (Fiesta 8 % debajo de 23 comparables) no era 🔥 con una referencia por modelo, que es el caso común.

## 2. Objetivo

1. Que «🔥 Oportunidad» sea verdad cuando se dice. La regla operativa del 05/11 (`MAILS_DE_PLAN.md`, «auto que te perdiste») dice: «precio creíble: entre 5 % y 35 % debajo… Más de 35 % suele ser un dato mal cargado… Un auto más caro que los comparables tampoco es una oportunidad». Lo mismo piden el PRD («No fingir certeza») y «Menos alertas, mejores alertas».
2. Que especificar más no condene una búsqueda, y que lo desconocido no cuente como un «no».
3. Que la alerta, la pestaña, el dashboard y los mails digan lo mismo: sin decaimiento y con la misma decisión en tarjeta y en detalle.
4. Que ninguna búsqueda actual pierda una oferta que era creíble cuando se decidió y que hoy alerta.
5. Mantener el volumen de alertas cerca del de hoy, con menos alertas débiles.

**No es objetivo:**
- Mejorar el ranking contra el comportamiento: ninguna candidata lo mejora de forma medible fuera de muestra.
- Arreglar el pool de comparables: es nacional, mezcla fuentes y tiene el sesgo ARS/USD.
- Ver el estado del auto.

## 3. La fórmula nueva

Notación:
- `d` = % debajo de la mediana de comparables (`price_ref.diff_pct`, positivo = más barato). En la tarjeta es el precio de la tarjeta contra la mediana guardada.
- `n`, `p25` y `level_used` salen del mismo `price_ref`.
- `clamp` = recortar a [0, 1].

### 3.1 Precio (`deal`, 0–1)

```
d_eff  = d − offset(fuente)                  offset = {kavak: 9}
s_lo   = 100·(1 − p25/mediana)               distancia de la mediana al cuartil barato (sin p25: d_full = 16)
d_full = clamp_[12, 20](2,5 · s_lo)          crédito completo a ~2,5 "spreads" debajo de la mediana
raw    = 0                          si d_eff ≤ −20
         0,4·(d_eff + 20)/20        si −20 < d_eff ≤ 0      (0,4 = «en la mediana»)
         0,4 + 0,6·d_eff/d_full     si 0 < d_eff ≤ d_full
         1                          si d_full < d_eff ≤ 35  (banda creíble)
         1 − 0,3·(d_eff − 35)/15    si 35 < d_eff < 50      (baja a 0,7: «verificá»)
         0,6                        si d ≥ 50               (sospechoso; nivel topeado)
r      = (0,5 + 0,5·clamp((n − 5)/15)) · (0,9 si el pool es de nivel 'model') · (0,3 si no hay año)
deal   = raw                        si raw ≤ 0,4            (lo caro nunca se acerca a «en línea»)
         0,4 + r·(raw − 0,4)        si raw > 0,4            (evidencia débil acerca lo barato a «en línea»)
deal   = desconocido si no hay precio, si el precio es de relleno (§3.5) o si hay menos de 5 comparables
```

Por qué cada pieza:
- **Anclado al spread.**
  - La dispersión es angosta: la mediana de p75/p25 es 1,18 y el p25 está a ~5–10 % debajo.
  - Un 8 % debajo vale más en una referencia apretada que en un pool ancho.
  - Con un spread típico (7,6 %), 🔥 pide 9,5 % debajo con referencia por versión y 10,6 % con referencia por modelo (§9.5).
  - Se eligió 2,5 (y no 2,0) por selectividad: con 2,0 hay muchas más 🔥 y 5 búsquedas con más de 25 % de 🔥.
- **Meseta hasta 35 %, caída hasta 50 %.**
  - Ese es el corte de la regla del 05/11.
  - Más allá de 40 % bajan los clics salientes (OR 0,71).
  - 3 de los 4 descartes explícitos estaban entre 33 y 59 % debajo.
- **Confiabilidad.** Con pocos comparables, un pool mezclado o sin año, la referencia promete menos y el precio se acerca a «en línea». No hay factor por sitio: el score describe el auto, no el sitio.
- **Solo del lado barato.** Un aviso sin año a USD 30.000 contra una mediana de 5.000 no sube a «coincidencia».
- **Kavak −9 puntos.** Es medido: contra la misma marca, modelo, año y tramo de km, Kavak publica 8–11 % debajo (§9.6). Un Kavak a −9 % es un Kavak típico.

### 3.2 Encaje (`fit`, 0–1)

Los filtros duros ya pasaron; si no, no es un match.

| preferencia | se cumple | no se cumple | sin dato |
|---|---|---|---|
| `price_target` | 1 | **graduado dentro del presupuesto**: 1 → 0,6 en `price_max` (sin máximo: → 0,4 a +15 %) | 0,75 |
| `km_target` | 1 | 1 → 0,4 a +30 % | 0,75 |
| vendedor (para la preferencia: «posible agencia» de F-02 o voz de agencia cuentan como agencia) | 1 | 0,4, y además tope de nivel (§3.3) | 0,75 |
| colores, distancia | 1 | 0,4 | 0,75 |
| versión preferida (no estricta) | 1 | otra versión 0,5 | 0,75 |

```
encaje_nivel = promedio de las preferencias que la búsqueda tiene (1 si no tiene)
encaje_score = encaje_nivel − 0,03 × filtros duros sin dato
```

- **Los cortes de nivel leen `encaje_nivel`; el score lee `encaje_score`** (regla 1 de F2).
  - Un filtro duro sin dato (caja, combustible, km) aparece en «A verificar» y ordena un poco más abajo dentro del nivel, pero no cambia el nivel.
  - Es lo que el spec de F decía que hacía, y no hacía: el −0,03 decidía el nivel en la 253.
  - Con esto, las decisiones que cambian entre tarjeta y detalle bajan de 54 a 22 de 1.883 en el extendido.
- **0,75 para lo desconocido** queda cerca del valor típico medido de las preferencias conocidas (`price_target` 0,86, vendedor 0,69, versión 0,67, `km_target` 0,60).
- **`price_target` graduado.** El usuario que pagó escribió «3500–4000» y el formulario guardó 3500 como ideal. Un auto dentro de su propio rango no puede puntuar como un «no».
- **Fallido = 0,4, no 0.** La UI promete «prioriza; no descarta».

**Voz de agencia** (regla 5 de F2):
- Un aviso que la fuente da como «particular», cuya descripción usa la voz de una agencia, cuenta como **posible agencia**, solo para la preferencia de vendedor.
- Ejemplos de esa voz: «financiamos», «tomamos/recibimos tu usado», «te lo compramos», «somos agencia», «nuestro local/salón», «horario de atención».
- La regla pide una frase en plural o dos señales distintas, y guarda la frase que la disparó para mostrarla.
- No cuentan las frases que también escribe un particular: «services en concesionario oficial», «financio», «no somos agencia».
- Solo existe con el detalle, porque la tarjeta no trae descripción. Por eso actúa justo en las búsquedas que ya esperan al detalle (§4.1).
- **No entra en `effective_seller`** (`intelligence/seller.py`), que también alimenta el filtro estricto PRO-01, el costo total, los duplicados y el corte de comparables por vendedor. Es un predicado aparte, que solo leen la preferencia y el tope de nivel (§4.7).

### 3.3 Niveles: qué significa «oportunidad»

Las reglas se evalúan en orden:

| nivel | regla |
|---|---|
| excluido | `price_partial`, o d ≥ 65 (como hoy) |
| 🔥 **oportunidad** (`high`) | precio ≥ 0,70, encaje_nivel ≥ 0,70, **0,6·precio + 0,4·encaje_nivel ≥ 0,82**, y ningún flag. Flags: sin precio (o de relleno), sin año, sin comparables, n < 10, d_eff > 35, d ≥ 50, vendedor sin dato en una búsqueda con preferencia de vendedor, vendedor confirmado distinto del pedido |
| 🟢 **buena** (`good`) | con precio, d < 50, con año, y alguna de las dos: **«buen precio»** = (precio ≥ 0,65 o descuento creíble: 5 ≤ d_eff ≤ 35 con n ≥ 10) y encaje_nivel ≥ 0,45; **«coincide, precio en línea»** = encaje_nivel ≥ 0,85 y d_eff ≥ −2 (o sin comparables) |
| 🟡 coincidencia (`match`) | encaje_nivel ≥ 0,30 y (sin precio, sin comparables, d_eff ≥ −10 o d ≥ 50) |
| ⚪ baja (`low`) | el resto: claramente más caro que el mercado, o encaje < 0,30 |
| **tope de vendedor** | si el vendedor confirmado es distinto del que pide la preferencia, un nivel «buena» o 🔥 baja a «coincidencia». El aviso se lista; alerta solo en las búsquedas que avisan desde «coincidencia» o «todo» |

**En palabras:**
- 🔥 = «Está X % debajo de N publicaciones comparables, es lo que buscás, y no hay nada del precio que verificar». Precio y encaje tienen que llegar juntos a un mínimo, con un piso en cada uno.
- 35–50 % debajo puede ser «buena» con «muy por debajo: verificá todo antes de señar» (el copy PAR-02 ya aprobado), nunca 🔥.
- 50 % o más es como mucho «coincidencia», con el texto de anticipo.
- Sin año, sin precio o con precio de relleno: como mucho «coincidencia». Se listan, pero nunca alertan en una búsqueda que avisa desde «buena».
- **Vendedor sin dato** (la tarjeta de FB o ML no lo trae) no es lo mismo que **vendedor distinto**. Sin dato vale 0,75, no puede ser 🔥 y la decisión espera al detalle. Distinto, con el dato confirmado, aplica el tope.

**Por qué la 🔥 combinada** (regla 3). Con F, el piso de precio 0,75 hacía que el ejemplo del PRD dependiera del nivel del pool. La regla combinada deja pasar un precio 0,70–0,75 si el encaje es alto, y deja afuera un precio alto con encaje justo. Suma 28 alertas 🔥 en el extendido, y las 🔥 alertadas pasan a 0,66 de las de hoy (con F, 0,57).

**Por qué el tope de vendedor** (regla 2). Una regla combinada sola no separa dos casos que sí hay que separar:
- en la 253 el encaje bajo viene de datos que faltan y de otra versión: hay que recuperarla;
- en la Corsa 97, dos publicaciones de agencia (157823 y 170382) tienen precio 0,80 con encaje 0,42–0,51, porque falló una preferencia explícita con el dato confirmado: no tienen que alertar.

Los dos casos están en el mismo rango, así que cualquier umbral que recupere uno vuelve a alertar el otro. Los cortes sin el −0,03 recuperan la 253; el tope mantiene en silencio a la 97.

### 3.4 Score 0–100

```
crudo = 100·(0,6·precio' + 0,4·encaje_score)     precio' = precio; 0,4 sin comparables; 0,2 sin precio
score = banda del nivel: 🔥 85–99 · buena 70–84 · coincidencia 50–69 · baja 0–49
        🔥: 85 + 14·clamp((crudo − 100·c_high)/(100 − 100·c_high))     c_high = 0,82
        buena: 70 + 14·clamp((crudo − 45)/50) · coincidencia: 50 + 19·clamp((crudo − 25)/60) · baja: 49·clamp(crudo/70)
```

- `score ≥ 85 ⇔ 🔥` sigue valiendo. Ordenar por score es ordenar por nivel y, dentro del nivel, por precio y encaje.
- **La banda 🔥 arranca en `c_high`**, no en `level_thresholds`. Si alguien edita `level_thresholds.high` en `/admin/config`, el corte y la banda no se pueden desincronizar. Esto corrige lo que decía el spec de F.
- Como el nivel lee `encaje_nivel` y el score `encaje_score`, una 🔥 puede tener un crudo menor que 82. Esas quedan en 85 y empatan; hay un test para eso.
- No llega a 100 («no fingir certeza»). No hay término de antigüedad.

### 3.5 Datos faltantes o que no son lo que dicen

| caso | efecto en F2 | hoy |
|---|---|---|
| km, transmisión, combustible, carrocería (filtro duro sin dato) | −0,03 en el score; no cambia el nivel; aparece en «A verificar» | −0,15 de match cada uno, más km 0,5 y completitud |
| una preferencia sin dato (vendedor, km ideal…) | 0,75 de esa preferencia; «A verificar» | 0 (cuenta como no cumplida) |
| vendedor sin dato, en una búsqueda con preferencia de vendedor | lo anterior, y no puede ser 🔥; en la tarjeta de FB o ML la decisión espera al detalle | 0, y además −0,15 si el filtro es estricto |
| vendedor confirmado distinto del pedido | 0,4 y como mucho «coincidencia» | 0 |
| año | la referencia vale ×0,3; como mucho «coincidencia» | −0,15; puede ser 🔥 |
| precio | precio desconocido; como mucho «coincidencia» | −0,15; podía ser «buena» |
| **precio de relleno**: 4 o más cifras iguales del 1 al 8 (USD 11.111, ARS 1.111.111) | como sin precio, con el texto «parece un número de relleno»; como mucho «coincidencia» | se usa como precio: el Golf a 11.111 salía «buena» (con F, 🔥) |
| menos de 10 comparables | la confiabilidad baja; no puede ser 🔥 | podía ser 🔥 (45 hoy) |
| fecha de publicación, descripción, fotos | nada (salen del score); la descripción solo cuenta para la voz de agencia | antigüedad y completitud |

**Precio de relleno, en detalle:**
- **Va como bandera, no como precio null.** Va en `attributes._price_placeholder` (`normalization/listing.normalize_listing`, junto a `doubtful_price`), y solo la lee f3.
  - Si se pusiera `price` en null, el filtro de precio daría «sin dato» y el aviso **pasaría a matchear**.
  - Hoy hay 46 avisos de FB a USD 1.111 y 12 a ARS 1.111.111 que no matchean con nadie. Con el precio en null entrarían a las listas.
- **El 9 no cuenta.** Los 9.999 son precios de vidriera: en ML a USD 9.999 están a −9 %, +3 % y −1 % de la mediana.
- **Si salen de los pools de comparables** se decide al pasar a real (decisión 3). Mueve medianas y no está medido.

**Lo que se sacó de F2 después de la verificación:** «el mismo precio en 3 o más autos de un vendedor de FB». La tarjeta de FB no trae vendedor, así que la regla no existe al decidir. Su efecto propio eran 30 avisos, 7 matches y 0 alertas, con precios redondos que pueden ser stock real.

### 3.6 Lo que el score no ve, y la palanca

- **El estado del auto y el año dentro del rango.** Con eso separó el usuario que pagó lo que guardó de lo que descartó: guardó un 2011 y descartó dos 2007 y un 2008. No hay una señal general de año en los datos, así que no entra en el score.
  - Palanca: el orden **«Año más nuevo»** en la lista (`web/lib/sorts.ts`, `search_results`), que no mueve scores. Va con otro nombre que «Más recientes», que ya existe y ordena por publicación.
- **La referencia de la decisión.** El backtest usa la mediana guardada, no la del momento de decidir. Cerca de los cortes de 5, 35 y 50 % alrededor del 15 % de los avisos puede cambiar de banda. §4.4 guarda la referencia de decisión para la próxima medición.

### 3.7 Qué lee la persona

Las cadenas van en `worker/intelligence/copy.py` y `web/lib/copy.ts`, y las cubre el lint de `FORBIDDEN_TERMS`.

**Reglas de redacción:**
- El número de «% debajo de comparables» es siempre el crudo (`diff_pct`), como hoy en la ficha y en el mail. El de Kavak ajustado va aparte, explicado.
- No se muestra el crudo 0–100 de §3.4: después de las bandas no coincide con el score visible.
- «Precio real» es un término prohibido por el lint y no llega a la UI.
- El tope de vendedor no dice «no te avisamos»: las búsquedas que avisan desde «todo» sí reciben esas alertas.

**Ficha, «¿Por qué tiene N?», con dos barras: Precio y Encaje.**
- 🔥: «🔥 Oportunidad · Precio: 26 % debajo de 129 publicaciones comparables · Encaje: precio sobre tu ideal (dentro de tu presupuesto) · A verificar: km, transmisión, combustible».
- Debajo de las barras: «Es oportunidad cuando precio y encaje, juntos, llegan al mínimo, con un mínimo en cada uno, y no hay nada del precio que verificar. Dentro de las oportunidades, ordenamos por precio (60 %) y encaje (40 %).»
- Cerca del corte: «Le faltó poco para oportunidad: con un precio un poco más bajo lo sería.» / «…si coincidiera en {preferencia} lo sería.»
- Dato faltante: «{datos} sin dato: no cambia el nivel; solo lo ordena un poco más abajo.»
- Buena muy por debajo: «🟢 Buen precio: 47 % debajo de 304 publicaciones comparables (muy por debajo: verificá todo antes de señar)».
- Sin año: «Precio: sin año informado lo comparamos contra todos los años del modelo; no la marcamos como oportunidad hasta conocer el año.»
- Precio de relleno: «Precio publicado: USD 11.111. Parece un número de relleno (todas las cifras iguales): lo tratamos como sin precio y no lo comparamos.»
- Voz de agencia: «Posible agencia (la descripción dice «{frase}»); la publicación dice particular».
- Kavak: «{d} % debajo del mercado observado (n={n}). Kavak suele publicar ~9 % debajo: contando eso, queda {d_eff} % debajo.» (o «…queda en línea.»)

**Textos de tope.** Reemplazan el fijo «limitado a Buena coincidencia» (`listings/[id]/page.tsx:655-660`) con una línea por motivo:
- «muy por debajo: como mucho Buena»
- «puede ser un anticipo: como mucho Coincidencia»
- «pocos comparables (n=…): no la llamamos oportunidad»
- «sin año» · «sin precio» · «precio de relleno: como mucho Coincidencia»
- «vendedor sin dato: lo confirmamos al leer el aviso»
- «otro tipo de vendedor que el que pediste: como mucho Coincidencia»

**Mails.**
- Asunto de la alerta 🔥: «🔥 Oportunidad · Corsa 2008 · 26 % debajo de publicaciones comparables y coincide con lo que buscás». Es la frase del PRD:187, ahora cierta por construcción.
- Alerta new_match: «🟢 Buen precio: 14 % debajo de comparables» o «🟢 Coincide con lo que buscás · precio en línea con el mercado».
- Notas:
  - «Ojo: otro tipo de vendedor que el que pediste ({kind}).»
  - «Ojo: posible agencia por la descripción («{frase}»).»
  - «Precio publicado USD 11.111: parece de relleno; consultá el precio.»
  - Kavak: «{d} % debajo de publicaciones comparables (Kavak suele publicar ~9 % debajo; contando eso, {d_eff} %).»

## 4. Cambios en el pipeline de alertas

### 4.1 Cuándo se decide

- **Regla.** Se decide con la tarjeta, como hoy. La excepción son las búsquedas con preferencia de vendedor: si su tarjeta de FB o ML no trae vendedor, la decisión **espera al detalle**.
- **Mecánica:**
  - `pipeline/scheduler.match_alert` guarda el match fresco con `decision_pending_at = now()` y no arma el `MatchCandidate`.
  - El re-score de enriquecimiento (`pipeline/enrich.py`, `rescore_changed`) llama a `decide_pending(listing_ids)`, que arma el candidato con los datos del detalle.
  - `decide_pending` vuelve a aplicar lo que hoy aplica `match_alert`: `_is_recent`, `matched_elsewhere`, `repost` y los silenciados.
  - Un barrido cada minuto decide, con lo que haya, los pendientes de más de **20 minutos**. El barrido es imprescindible: `rescore_changed` solo re-puntúa si el detalle emitió `listing_updated`. Con 10 minutos, la 170382 (agencia, Corsa 97) habría alertado, porque su detalle llegó a los 10,6 min.
- **Dedupe y tope.** La clave de dedupe `match:<listing_id>` no cambia. El tope diario se cuenta al decidir.
- **Bandera.** Va detrás de `app_config.alerts.defer_seller_pref`. Ponerla en false drena los pendientes en el próximo minuto.
- **Alcance hoy:** 4 de las 81 búsquedas habilitadas tienen preferencia de vendedor (3 son del usuario que pagó), y ninguna usa el filtro estricto.

**Qué regla se puede calcular al decidir:**

| regla | dato | en la tarjeta | en el detalle |
|---|---|---|---|
| 1. cortes sin el −0,03 | `MatchResult.unknown` | sí | sí |
| 2. tope de vendedor | `result.soft["seller_type"]` | si la tarjeta trae vendedor | sí |
| 3. 🔥 combinada | precio y encaje | sí | sí |
| 4. precio de relleno | `listings.price` | **sí**: las 2 alertas del Golf a 11.111 salieron con ese precio | sí |
| 5. voz de agencia | `listings.description` | no | sí; actúa en búsquedas que esperan al detalle |
| 6. «Sold ·» | `listings.title` | **no**: lo escribe una relectura posterior | en las relecturas: va al colector (§4.6) |
| Kavak −9 | fuente y `price_ref` | sí | sí |

### 4.2 Subidas de nivel

Un re-score sigue sin alertar. Alertar cuando sube el nivel exige una clave de dedupe nueva y una regla de tope, y con F2 casi no hace falta: tarjeta y detalle casi siempre coinciden y no hay decaimiento. Si en la sombra aparecen subidas relevantes (por ejemplo, un precio que se corrige), se diseña aparte.

### 4.3 Dedupe de duplicados

- **Regla.** Un match fresco no alerta si su aviso es el mismo auto que otro ya alertado al mismo usuario en la misma búsqueda en los últimos 30 días.
- **Mismo auto** = un par en `listing_duplicates` (cualquier tipo) o en `probable_repost_of`, o misma fuente, modelo, año y precio redondeado.
- **Copy.** El aviso de la alerta original suma «también publicado acá». La alerta de re-publicación (`repost`) sigue igual.
- **Medido:** 103 → 99 alertas en el conjunto actual y 831 → 779 en el extendido.
- Usa señales de PAR-02 resto solo para alertas, no para el score ni el nivel.

### 4.4 Registro de la decisión y modo sombra

**Tabla nueva, solo de inserción: `match_decisions`.**
- **Qué guarda.** Una fila por candidato fresco, se alerte o no:
  - match, búsqueda, `decided_at` y fase (`card` | `deferred` | `sweeper`);
  - `scoring_version`, score, nivel, precio, encaje y flags;
  - el tipo de alerta, o el motivo si no alerta;
  - el `price_ref` usado (n, mediana, p25, p75, `level_used`, `diff_pct`);
  - el precio, el título y el vendedor de ese momento;
  - en modo sombra, la decisión de la otra fórmula.
- **Clave única** `(match_id, modelo, fase)`, para que un lote reintentado no duplique.
- **Fase tarjeta.** Se escribe en `Notifier.on_matches` (`notifications/service.py`), que tiene los candidatos frescos y su audiencia.
  - Para f2 se guarda el `engine.classify` real.
  - Para f3, el mismo `classify` con el nivel sombra, como hipótesis pura.
- **Fase detalle.**
  - La fila de tarjeta lleva `would_defer`.
  - Después del re-score de enriquecimiento se inserta la fila `deferred`.
  - Para las que siguen abiertas a los 20 min, el barrido inserta `sweeper`.
- **Por qué hace falta.** `score_breakdown` se pisa en cada re-score (`matches.upsert_scored`), así que no sirve como registro. Durante la sombra, `score_breakdown.shadow_f3` es la vista actual de f3: la web la ignora, porque filtra por `COMPONENTS`.
- **Payload de la notificación.** Suma `scoring_version`, el `price_ref` de decisión y `deal_d` (= d_eff) en `notifications/service.match_payload`.

### 4.5 Prioridad, tope diario y digest

- `engine._priority` pasa a (nivel, score, más reciente primero): la antigüedad sale del score pero sigue desempatando. El digest desempata igual.
- El tope diario por plan y la cuota de la prueba no cambian.
- **Umbral Pro.** `engine._reached` lee `deal_d`, con `diff_pct` como respaldo para los payloads viejos. Es la decisión 4: hoy ninguna búsqueda tiene umbral Pro, así que no mueve ninguna alerta actual.

### 4.6 «Sold ·» en Facebook: arreglo del colector, aparte del score

- **Qué pasa hoy.** Hay 56 avisos de FB con título «Sold ·» o «Vendido ·», todos `active`. La ficha vendida no contiene ninguno de los `_GONE_TEXTS` de `facebook.py`. FB sí pasa avisos a `gone` por otras vías: 1.237 de 7.009 en 60 días.
- **Por qué no va en el score.** El título vendido lo escribe una relectura posterior. Ninguna de las 15 alertas que se mandaron sobre avisos que hoy dicen «Sold» tenía ese título al enviarse. Una regla de score sobre el título no cambiaría ninguna decisión: en el backtest parecía bloquear 4 alertas, pero era información del futuro.
- **Arreglo.**
  - `collectors/facebook.parse_detail` devuelve `ListingDetail(gone=True, …)` si el `h1` empieza con «Sold ·», «Vendido ·», «Pending ·» o «Pendiente ·», como ya pasa con el «vendido» de autocosmos (TECHNICAL_PLAN:376).
  - `DETAIL_PARSER_VERSION` pasa de 3 a 4, más un test del parser.
  - `ingest_detail` ya emite `listing_gone`, así que la pestaña, el dashboard y los seguidores lo reciben sin cambios.
- **Pools.** El aviso terminado **sigue en los pools** como cualquier `gone` («los gone cuentan»).
- **Tamaño y fecha.** Son ~10 líneas y puede salir ya. Mueve un poco la línea base de f2, porque los vendidos dejan de listarse, así que hay que anotar la fecha para la sombra.

### 4.7 Dónde vive la voz de agencia

- **Cálculo.** Va en `normalization/description_facts.py`, como un claim `dealer_voice` con la frase que lo disparó, dentro de `description_facts` (jsonb, sin migración).
- **Predicado.** `seller_for_preference(listing)` en `intelligence/seller.py`, con su gemelo en `web/lib/seller.ts`. Lo leen solo `matching._preferences` y el tope de f3.
- **Por qué no va en `effective_seller`.** Ahí movería el filtro estricto PRO-01 (borraría matches), PAR-01, los duplicados y el corte de `price_ref` por vendedor de F-02 (movería medianas).
- **El principio de `seller.py` se rompe.** Dice que todo consumidor que trata a un vendedor como agencia lo lee de ahí. Juan lo tiene que aceptar (decisión 2).
- **Relleno.** Los avisos ya guardados necesitan una pasada de `tools/reprocess.py --raw`, o el cálculo en vivo desde `description`, que `rows_for_scoring` ya trae.

## 5. Nivel guardado y decaimiento

- **Sin término de antigüedad, el nivel guardado solo cambia si cambian los datos o la referencia.** La alerta, la pestaña, el dashboard y los mails leen lo mismo. Hoy hay 39 🔥 guardadas contra 130 al decidir.
- `rescore.every_hours` vuelve a 24.
  - El re-score también refresca `price_ref` y borra los matches que dejaron de cumplir. A 24 h, las dos cosas pasan 4 veces menos seguido.
  - No hay registro de por qué se puso en 6 h el 25/10.
- La línea «publicado hace N h» queda como información (peso 0). Para ML conviene `first_seen_at`, porque `published_at` viene corrido ~24 h.

## 6. Conteos «por debajo de comparables» en los mails

- **Hoy.** Cuentan `level = 'high'` decaído y sin filtrar el estado del aviso:
  - los niveles de `claim_lifecycle_emails*`: `_welcome`, `_base` y `trial_reserve` (`below_n`);
  - `record_trial_ends`, `record_bonus_trial_ends` y `missed_since_expiry`;
  - `free-result-limit.tsx` y `expired-missed.tsx`.
- **Propuesta.** Contar **ofertas creíbles vivas y sin duplicados**:
  - precio conocido y que no es de relleno, 5 ≤ d_eff ≤ 35, n ≥ 10, con año y d < 50 (es la regla del 05/11, que ya usa `missed_car`);
  - aviso `active`;
  - un auto contado una vez, como en la pestaña.
  - La condición se guarda como `score_breakdown.deal_tier`. Las funciones SQL la leen en una migración que hace `create or replace` de cada capa.
  - `expired_search_matches` no guarda año, `n` ni fuente: hace falta una columna (`deal_tier`) o seguir contando por nivel ahí.
- **Medido (22:55):**
  - 39 → **589** matches «por debajo», en 15 → 47 búsquedas;
  - para el usuario que pagó, Gol 0 → 4, Clio 0 → 1 y Corsa 0 → 2;
  - el texto no cambia y ahora es cierto.
- **Dashboard.** «M oportunidades esta semana» cuenta solo 🔥 frescas, sin backfill. Si no, una búsqueda nueva mostraría decenas de «oportunidades» de golpe (la 382 tiene 59).

## 7. Consumidores que cambian

| grupo | qué cambia | archivos |
|---|---|---|
| 1. Vocabulario de niveles | Nada estructural: no hay nivel nuevo ni cambia el enum. | `copy.ts`, `copy.py` |
| 2. «Oportunidad = high» | El motor no cambia. Cambia el significado: 🔥 visibles 124 → 294 vivas (273 autos distintos), casi todas de backfill. Los mails cuentan ofertas creíbles (§6). La pestaña agrupa duplicados y el dashboard cuenta 🔥 frescas. | `search_results`, `search_result_counts`, `dashboard_summary`, `claim_lifecycle_emails*`, `record_*`, `missed_*`, `free-result-limit.tsx`, `expired-missed.tsx` |
| 3. «Valioso = buena o más» | `low` baja de 22,8 % a 17,3 % de los matches. `matched_recheck_queue` (`<> 'low'`) relee ~7 % más avisos, con tope por fuente. El trigger `observe_admin_first_good` se dispara en el re-score del cambio: se anota la ventana y se excluye de `v_first_value`. | trigger, `admin_decision_metrics` |
| 4. Fórmula y componentes | `COMPONENTS = ("deal", "fit")`, con etiquetas «Precio» y «Encaje». El breakdown guarda `deal`, `fit`, `deal_tier`, `flags` y `a_verificar`. La web dibuja las dos formas por `scoring_version`, porque los matches de avisos vendidos y de búsquedas sin acceso no se re-puntúan. | `config.py`, `scoring.py`, `levels.py`, `copy.py`, `explain_match.py`, `web/lib/copy.ts`, `listings/[id]/page.tsx`, `admin/inspector.tsx`, `web/lib/types.ts` |
| 5. Vendedor | Predicado `seller_for_preference` (voz de agencia) en Python y TS. `effective_seller` no cambia. | `intelligence/seller.py`, `web/lib/seller.ts`, `normalization/description_facts.py`, `matching.py` |
| 6. Precio | Bandera `_price_placeholder` que solo lee f3. Las guardas 50/65 y las bandas de `much_cheaper` 25/35/50 no se mueven. | `normalization/listing.py` |
| 7. Pro | `deal_d` en el payload; `_reached` lo lee. | `notifications/service.py`, `notifications/engine.py` |
| 8. Colector FB | «Sold/Vendido/Pending ·» = `gone` (§4.6). | `collectors/facebook.py` |
| 9. Propagación | Un bump: el re-score de arranque toca ~2,5 mil filas en ~3 min y no alerta. | `rescore.py` |
| 10. Validación | Cotas para todas las claves nuevas (§8). | `web/lib/admin-config.ts`, `config._merge` |

## 8. Configuración, validación y `SCORING_VERSION`

- **Clave nueva y versionada.** `app_config.score_model_f3` = {`mode`: off|shadow|live, `deal`, `fit`, `levels`, `rules`}. Solo la lee f3.
- **Las claves de hoy no se tocan.** `score_weights` y `score_curves` guardan valores explícitos que `_merge` superpone a los defaults. Si f3 los reutilizara, un deploy o un rollback mezclaría fórmulas.
- **Versión.** `SCORING_VERSION = "f3-precio-encaje"` cuando `mode = live`. En `off` o `shadow` se sigue escribiendo `f2-v5-seller-margin`. Es un solo bump por deploy. Cambia `test_seller_classification::test_scoring_version_is_the_one_shared_with_pro02`.
- **Cotas** en `validateConfigChange` (`admin-config.ts`), espejadas en `_merge`:

| clave | cota |
|---|---|
| `deal.d_floor` < `deal.d_ceil` | dentro de [5, 30] |
| `deal.d_mult` | [1, 4] |
| `deal.cred_max` | [20, 50] y < `d_susp` |
| `deal.d_susp` | = `guards.suspicious_pct` |
| `deal.r_model`, `deal.r_noyear` | [0,1, 1] |
| `deal.kavak_offset` | [0, 20] |
| `fit.unknown`, `fit.fail`, `fit.trim_other` | [0, 1], con `fail` ≤ `unknown` |
| `fit.unknown_hard` | [0, 0,15] |
| `fit.price_target_at_max` | [0,3, 1] |
| `levels.x_high`, `levels.y_high` | [0,5, 0,95] |
| `levels.c_high` | [0,70, 0,95] y ≥ 0,6·`x_high` + 0,4·`y_high` (si no, la regla no hace nada) |
| `levels.x_good` < `x_high`; `levels.y_deal` < `y_high`; `levels.y_good` > `y_min` | – |
| `levels.n_min_high` | ≥ `comparables.min_n` |
| `levels.fair_min_d` | [−10, 5] |
| `rules.seller_cap`, `rules.agency_voice`, `rules.placeholder` | booleanos |
| `mode` | ∈ {off, shadow, live} |
| todas las claves | números finitos, sin cadenas (hoy un `"80"` frena todo el scoring) |

Los valores propuestos y su sensibilidad están en §14, «Parámetros».

## 9. Resultados en las búsquedas actuales

### 9.1 Conjunto actual

Corrida de las 21:38 y 21:41 UTC (dos mitades). Son 79 búsquedas, 67 con matches y 42 con frescos; 3.196 matches y 256 frescos. «Alertas» = alertas inmediatas posibles (fresco y nivel ≥ `notify_min_level`), antes del tope diario y la cuota de prueba.

| métrica | hoy · tarjeta | F · decisión | **F2 · decisión** |
|---|---|---|---|
| alertas (sin duplicados) | 111 (107) | 105 (101) | **103 (99)** |
| alertas 🔥 (sin duplicados) | 32 (30) | 22 (20) | **22 (20)** |
| búsquedas con frescos y 0 alertas (de 42) | 14 | 12 | **13** |
| búsquedas en silencio respecto de hoy | – | 2 (345 sin precio, 371 con n < 10) | **2** (las mismas) |
| alertas creíbles perdidas al decidir | – | 0 | **0** |
| ofertas creíbles frescas alertadas al decidir (de 50) | 47 | 48 | **47** |
| alertas sobre la mediana · a más de 2 % | 8 · 4 | 10 · 3 | **10 · 3** |
| alertas a ≥ 50 % debajo (cualquier nivel) | 11 | 3 | **3** (como «coincidencia», en búsquedas que avisan desde «todo» o «coincidencia») |
| alertas a «buena» o más sin año / con anticipo / sin precio | 11 / 9 / 3 | 0 / 0 / 0 | **0 / 0 / 0** |
| 🔥 en listas (creíbles / sospechosas) | 132 (76 / 56) | 333 (332 / 1) | **356 (355 / 1)** |
| 🔥 vivas · vivas y autos distintos | 124 · 120 | 270 · 244 | **294 · 273** |
| 🔥 basura en listas («Sold» o precio de relleno) | 1 | 12 | **0** |
| 🔥 a más de 35 % · sin año o n < 10 · otra versión | 14 · 45 · 0 | 1 · 0 · 1 | **1 · 0 · 3** |
| búsquedas con ≥ 1 🔥 | 20 | 39 | **37** |
| con ≥ 6 / ≥ 8 restricciones y 🔥 (de 12 / 6) | 0 / 0 | 5 / 3 | **5 / 3** |
| corr(restricciones, score medio) | −0,315 | +0,066 | **+0,053** (frágil: +0,026 a las 22:25; mitad par −0,04) |
| búsquedas (n ≥ 20) con más de 25 % · más de 40 % de 🔥 · máximo | 1 · 0 · 29 % | 3 · 0 · 34 % | **4 · 1 · 43 %** (la 366) |
| % de matches en `low` · matches con 100/100 | 22,8 · 0 | 17,4 · 0 | **17,3 · 0** |
| tarjeta ≠ detalle en frescos: alertas · niveles (de 256) | – | 6 · 8 | **7 · 9** |

- **Réplica.** La verificación lo volvió a correr de cero a las 22:25, con otro tail. Dio 109 · 33 → 103 · 22 → 101 · 22 en alertas y alertas 🔥, y 132 → 334 → 355 en 🔥 en listas, dentro de la deriva de los datos vivos.
- **«Sold».** La F2 medida bloqueaba la 429256 de la 350 por su título de hoy. Con la regla en el colector (§4.6) esa alerta vuelve (104 alertas), porque al decidir el aviso no decía «Sold».

### 9.2 Conjunto extendido

Alertas: frescos, en dos mitades (22:01 y 22:04). Listas: todos los matches, en cuatro partes. Son 269 búsquedas con matches y 181 con frescos.

| métrica | hoy · tarjeta | F · decisión | **F2 · decisión** |
|---|---|---|---|
| alertas (sin duplicados) | 868 (807) | 808 (754) | **831 (779)** |
| alertas 🔥 · razón contra hoy | 262 | 150 · 0,57 | **173 · 0,66** |
| búsquedas con frescos y 0 alertas (de 181) | 39 | 36 | **37** |
| en silencio · despiertan | – | 10 · 13 | **10 · 12** |
| alertas creíbles perdidas: con el `diff_pct` guardado / con Kavak −9 / al decidir (búsquedas) | – | 26 (7) / 21 (5) / 19 (3) | **14 (9) / 9 (6) / 0** |
| ofertas creíbles frescas alertadas al decidir (de 393) | 363 | 358 | **386** |
| alertas a «buena» o más sin año, sin precio o con anticipo | 73 | 0 | **0** |
| alertas basura (precio de relleno o «Sold») | 10 | 10 | **6 bloqueadas al decidir** (los Golf a 11.111); las 4 «Sold» habrían salido igual |
| alertas sobre otra versión | 146 | 86 | **119** (efecto buscado en la 253) |
| 🔥 en listas (vivas) | 928 (825) | 1.234 (1.047) | **1.347 (1.164)** |
| con ≥ 6 / ≥ 8 restricciones y 🔥 (de 44 / 14) | 3 / 0 | 18 / 5 | **21 / 4** |
| corr(restricciones, score medio) | −0,260 | +0,068 | **+0,062** (mitad impar, negativa) |
| n ≥ 20 con más de 40 % de 🔥 | 0 | 2 (148, 307) | **2 (307, 366)** |
| tarjeta ≠ detalle en frescos: alertas · niveles (de 1.883) | – | 54 · 65 | **22 · 32** |

- **Las 14 alertas que F2 deja de mandar** y que serían creíbles según el `diff_pct` guardado:
  - 6 son de Kavak a su precio típico (37, 226 ×3, 253 y 303), con un d ajustado al decidir de −5 a 4 %;
  - 1 es la 51-142297, cuyo precio de tarjeta estaba 50 % o más debajo;
  - 6 son el mismo VW Golf 2017 a USD 11.111 (93, 148 ×3, 266 ×2). Su descripción dice «Anticipo mínimo + cuotas fijas»;
  - 1 es la 350-429256, «Sold» hoy y vivo al decidir: vuelve con la regla en el colector.
- **Con una definición independiente de «creíble al decidir»** (verificación), F2 pierde 7 alertas, todas basura: los 6 Golf y la 350. Sin la basura pierde 0. Sin el −9 de Kavak perdería 12. F pierde 19: 253 ×17, 129 y 197.
- **Mitades por paridad de `search_id`.**
  - Se sostienen en las dos: 0 creíbles perdidas al decidir, la credibilidad de las 🔥 y 0 alertas malas a «buena» o más.
  - No se sostienen en las dos: «búsquedas con frescos y 0 alertas» y el signo de la correlación.
  - Lo que corrige F2 está casi todo en la mitad impar: la 253 y la 129.

### 9.3 Búsqueda por búsqueda

Clasificación de F2 contra hoy (detalle en el [anexo por búsqueda](2026-11-08-recalibracion-score-por-busqueda.md)):

| conjunto | mejora | igual | menos ruido | silencio o empeora |
|---|---|---|---|---|
| actual, 21:38 (67 con matches; `diff_pct` guardado) | 5 | 52 | 7 | 3 (350 por «Sold», 345 sin precio, 371 con n < 10) |
| actual, 22:25 (68 con matches; al decidir, contando silencios) | 5 | 53 | 8 | 2 silencios (345, 371) |
| extendido (181 con frescos; `diff_pct` guardado) | 38 | 91 | 33 | 19 |
| extendido (al decidir, contando silencios) | 43 | 91 | 37 | 10 silencios, 0 pérdidas creíbles |

- **Los 10 silencios del extendido:**
  - 36, 76, 82 y 371: menos de 10 comparables;
  - 67 y 235: sin año;
  - 306: todas a 50 % o más debajo o sin año;
  - 43: otra versión;
  - 345: sin precio;
  - 89: «Sold» (artefacto: en producción habría alertado).
  - Todos están en la lista del criterio 2 ampliado.
- **Corrida por búsqueda de las 22:55**, en las 77 búsquedas actuales a esa hora:
  - alertas 103 → 97 → 95;
  - mejoran 5 (92, 341, 358, 366, 372);
  - menos ruido 6 (329, 334, 338, 342, 350, 357);
  - silencio 2 (345, 371);
  - ninguna pierde una alerta creíble al decidir.
- **F2 contra F:**
  - en la 97, F mandaba la 🔥 264835 y F2 no;
  - en la 350, la «Sold».
  - En el extendido, F2 recupera las 17 de la 253 y las de la 129 y la 197.

### 9.4 El usuario que pagó

Detalle aviso por aviso en el anexo. Los 23 matches dan los mismos scores y niveles en las dos corridas.

| búsqueda | alertas hoy → F → F2 | 🔥 en la lista hoy → F2 | qué alerta F2 | «por debajo» en el mail |
|---|---|---|---|---|
| 92 Gol | 0 → 1 → **1** | 0 → 3 | 409916 (2012, 47 % debajo) como 🟢 «verificá» | 0 → 4 |
| 95 Clio (avisa desde «todo») | 2 → 2 → **2** | 0 → 0 | las mismas de hoy: 296345 (coincidencia, anticipo) y 372908 (coincidencia: es agencia y él pide particular) | 0 → 1 |
| 97 Corsa | 0 → 1 → **0** | 0 → 0 | nada | 0 → 2 |

- **264835 (Corsa).** FB la da como particular, pero su descripción tiene voz de agencia: «recibimos tu usado», «te lo compramos», «solo DNI + anticipo», «cuotas fijas». Con la regla de voz de agencia queda en «coincidencia» 68 y no alerta; sin esa regla vuelve a ser 🔥 (medido). Sus dos descartes por vendedor eran agencias de FB. Es la decisión 2.
- **Las dos publicaciones de agencia de la Corsa** (157823 y 170382) siguen sin alertar gracias al tope de vendedor.
- **Falla que queda.** Su 2007 descartado (157185) es 🔥 93, arriba del 2011 guardado (80, «verificá»).

### 9.5 Ejemplo del PRD (Fiesta 8 % debajo de 23 comparables)

| referencia | F | F2 |
|---|---|---|
| por versión (la del test) | 🔥 92 | 🔥 **88** |
| por modelo | «buena» | 🔥 **86** |

- `GoldenFixtureTests` vuelve a caer dentro de **85–90** (88): no hace falta ampliar la banda del test. La OG «88/100» y el «87/100» del PRD:187 son verosímiles.
- **No es robusto al spread.** «8 % debajo» es 🔥 solo si el cuartil barato está como mucho a 6,4 % de la mediana (por versión) o a 5,8 % (por modelo). Con el spread típico, 🔥 pide 9,5 % o 10,6 %.
- **Propuesta de texto para el PRD:187 y la landing:** «11 % debajo de 23 publicaciones similares», que da 🔥 87 / 86. La otra opción es explicar la referencia apretada.

### 9.6 Kavak

- **Precio contra la misma celda** (marca, modelo, año y tramo de km; avisos de 60 días). La mediana Kavak / otros es:
  - 0,891 contra todo lo que no es Kavak (733 celdas, p25–p75 0,82–0,95);
  - 0,907 contra ML en pesos y 0,923 contra las agencias de ML en pesos;
  - 0,902 contra las agencias en pesos de todas las fuentes;
  - 0,901 con tramos de 10.000 km. Los km son iguales (razón 0,995).
- **Lectura.** Kavak publica 8–11 % por debajo del mismo auto. Es su política de precio fijo, no una oferta.
  - El supuesto de fondo: el resto se negocia ~9 %. Eso no está medido.
- **Dentro de Kavak el d sigue ordenando.** La baja en 7 días sube con el descuento: 2,9 % → 7,6 % → 14,0 %. El −9 corre a todos por igual.

### 9.7 Ranking contra el comportamiento

No se reclama ninguna mejora de ranking. Con F, los AUC dentro de cada búsqueda cambian de signo entre mitades al controlar la posición en la lista, y F2 no los volvió a medir.
- Que el 99,7 % de las 🔥 sean creíbles es **la regla haciendo lo que dice**, no evidencia de que la regla sea buena.
- Eso lo tiene que mostrar el modo sombra, con clics y salidas de las alertas que mandan las dos fórmulas (§11).

## 10. Tests

**Cambian:**
- **`worker/tests/test_intelligence.py`:**
  - `GoldenFixtureTests`: el Fiesta da 🔥 88 y la banda **sigue en 85–90**. Cambian los valores por componente y los textos.
  - `SellerPreferencePinTests.PINNED` (12 casos), `UnknownTests` (0,75 / −0,03 solo en el score) y `ConfigTests`.
  - `GuardAndLevelTests`:
    - 55 % debajo pasa a «coincidencia» (hoy ≥ 85 topeado en «buena»);
    - 73 % sigue excluido;
    - con menos de 5 comparables el precio queda desconocido;
    - se van los tests de vida media de 24 h.
- `test_pro01_seller_filter.py`: vendedor sin dato con el filtro estricto resta 0,03 en el score y no puede ser 🔥.
- `test_seller_classification.py`: el string de versión.
- `test_intelligence_copy.py`: los textos nuevos, incluido que «precio real» no aparezca.
- **DB:**
  - `test_ingest_postgres`: el aviso a 27 % debajo necesita 10 o más comparables para ser 🔥.
  - `test_intelligence_postgres`: «enriquecer sube el score» se prueba con un fallo conocido, no con un desconocido que se completa.
  - `test_margin_postgres`: convergencia por versión.

**Nuevos:**
- **Curva y referencia:**
  - la curva de precio es monótona hasta 35 % y baja después;
  - con el mismo d, una referencia más débil da menos precio, pero nunca por encima de su valor crudo cuando es cara;
  - el ajuste de Kavak.
- **Niveles:**
  - cada rama de la tabla de niveles, con sus flags;
  - la 🔥 combinada: precio 0,72 con encaje 1 es 🔥 (0,83), y precio 0,80 con encaje 0,70 no lo es (0,76);
  - `score ≥ 85 ⇔ 🔥`, con la banda anclada en `c_high`, incluido el empate en 85 cuando el crudo es menor que 82;
  - un filtro duro sin dato no cambia el nivel, solo el score.
- **Encaje:**
  - una preferencia sin dato nunca puntúa por debajo de una fallida;
  - `price_target` dentro de `price_max` nunca baja de 0,6.
- **Vendedor:**
  - tope de vendedor: confirmado distinto, como mucho «coincidencia»; sin dato, sin tope pero sin 🔥;
  - voz de agencia: los casos positivos («recibimos tu usado», «financiamos») y los negativos («services en concesionario oficial», «financio», «no somos agencia»);
  - el predicado no cambia `effective_seller`, ni el filtro estricto, ni los duplicados.
- **Precio de relleno:**
  - USD 11.111 y ARS 1.111.111 son relleno; USD 9.999 no lo es;
  - la bandera no cambia el conjunto de matches.
- **Pipeline:**
  - la espera al detalle: un pendiente se decide en el re-score de enriquecimiento o por el barrido, una sola vez;
  - el dedupe de duplicados;
  - `match_decisions`: una fila por fase, sin duplicar en reintentos.
- **Colector:** `facebook.parse_detail` con un `h1` «Sold ·», «Vendido ·» o «Pending ·» devuelve `gone`.
- **Pro:** `_reached` lee `deal_d`, y cae a `diff_pct` en un payload viejo.
- **Config:** las cotas de `validateConfigChange` rechazan cadenas, umbrales desordenados, un `c_high` que no hace nada y un `mode` inválido.
- **Web:**
  - `ScoreInWords` con las dos formas de breakdown (f2 y f3);
  - Vitest de los textos de tope y snapshot de las dos barras.
- **pgTAP:** `match_decisions` es solo de inserción, y los conteos «por debajo» usan la condición creíble y viva.

**No cambian:** los pgTAP y e2e que insertan scores literales, y `test_par02_risk_flags` (ninguna señal PAR-02 mueve el score).

## 11. Despliegue: modo sombra y criterios para pasar a real

1. **Arreglo del colector de FB (§4.6), ya y aparte** (decisión 3). Se anota la fecha porque cambia un poco la línea base.
2. **PR único** con código, tests, docs (`TECHNICAL_PLAN.md` §6.3–6.4 y PRD §20) y las migraciones:
   - `match_decisions`
   - `matches.decision_pending_at`
   - la fila `score_model_f3` con `mode = 'shadow'`
   - `alerts.defer_seller_pref = false`

   Se aplica con el OK de Juan. Antes de nombrar las migraciones se relee `max(version)`.
3. **Sombra, 10–14 días.**
   - Las alertas, los scores, los niveles, las listas y los mails siguen saliendo de f2.
   - El worker calcula f3 en cada evaluación y lo guarda en `score_breakdown.shadow_f3` y en `match_decisions`, en tarjeta y en detalle.
   - Las reglas 4 y 5 son banderas que f2 no lee.
   - Cada día se vuelve a correr el backtest de solo lectura y se publica la tabla por búsqueda.
4. **Criterios para pasar a real.**
   - Se fijan antes de empezar, con los parámetros de §14 congelados. Si en la sombra hay que mover un parámetro, se mueve por config y la medición vuelve a empezar desde ese día.
   - Se miden por búsqueda sobre las decisiones frescas del período, **leyendo `match_decisions`**: precio, título, vendedor y referencia del momento de decidir, no el estado de hoy de `listings`.

   Los criterios:
   1. Ninguna búsqueda pierde una alerta que f2 envió y que **era creíble al decidir**: precio de la tarjeta 5–35 % debajo con el −9 de Kavak, 10 o más comparables, año conocido, precio que no es de relleno y aviso vivo.
   2. Una búsqueda que f3 deja en silencio solo se acepta si todas sus alertas perdidas eran sin precio, de relleno, sin año, ≥ 50 % debajo, más de 2 % sobre la mediana, de otra versión, con menos de 10 comparables o de un aviso ya vendido. Cada una se lista para Juan.
   3. Alertas de f3 / alertas de f2 entre 0,85 y 1,10 (backtest: 0,93 actual y 0,96 extendido). Alertas 🔥 de f3 ≥ 0,6× las de f2 (backtest: 0,69 y 0,66). Se informa también contra las 🔥 creíbles de f2 (backtest: 22/20 = 1,10 y 173/197 = 0,88).
   4. 0 alertas de f3 a «buena» o más con aviso sin año, sin precio o con el precio de la tarjeta ≥ 50 % debajo.
   5. Tarjeta ≠ detalle en f3 en no más del 5 % de las decisiones frescas (backtest: 2,7 % y 1,2 %).
   6. Concentración: según la decisión 6. La propuesta es contar 🔥 vivas y autos distintos y listar para revisión toda búsqueda con 20 o más matches que pase el 40 %, sin bloquear.
   7. Solo se informa, sin que sea condición: clics y salidas de las alertas que mandaron las dos fórmulas, separados por el nivel de f3. Es la prueba del PRD:733 con etiquetas que la regla no ve. Con ~100 alertas no alcanza para decidir.
5. **Paso a real:** un deploy con `mode = 'live'` (bump a f3) y `defer_seller_pref = true`. El re-score de arranque toca ~2,5 mil filas en ~3 min y no alerta.
   - En el mismo deploy salen los conteos de mails (§6), la pestaña agrupada, el dashboard, la web con las dos formas de breakdown y, si Juan lo decide, la salida de los precios de relleno de los pools.
   - Se anota la ventana para `first_good_at`.
6. **Siete días de seguimiento diario:**
   - alertas 🔥 y new_match por búsqueda y por día;
   - porcentaje de 🔥 creíbles;
   - `v_high_score_engagement` separado por `scoring_version`;
   - pendientes resueltos por el barrido;
   - topes por vendedor y por voz de agencia, con su frase.

## 12. Rollback

- **Sin deploy:** `score_model_f3.mode = 'off'` y reinicio del worker. `rescore_outdated` vuelve a puntuar con f2 las ~2,5 mil filas activas en ~3 min. `alerts.defer_seller_pref = false` drena los pendientes en el próximo minuto.
- **Por qué es limpio:** las claves de f2 (`score_weights` y `score_curves`) y `effective_seller` nunca se tocaron, y las banderas nuevas solo las lee f3.
- **Lo que no vuelve:** las alertas ya enviadas. El conteo de mails conviene revertirlo en la misma migración inversa.
- **Lo que no se borra:** `match_decisions` queda. No se borran matches: las exclusiones (65 % y `price_partial`) no cambian.
- **El arreglo del colector** es independiente. Se revierte con su propio deploy, y el parser vuelve a la versión 3.

## 13. Riesgos y lo que no sabemos

1. **Crece la pestaña «Oportunidades».** Las 🔥 pasan de 132 a 356 (294 vivas). Casi todas son backfill de búsquedas nuevas, como la 382 con 59. Son creíbles, pero el PRD ilustra ~1 de cada 7.
   - Mitigación: agrupar duplicados, contar solo frescas en el dashboard y, si hace falta, subir `c_high` (0,84: 319 🔥).
2. **Concentración sin arreglo en la fórmula.**
   - La 307 (Gol, prueba vencida) tiene 30 🔥 de 47 matches (64 %). Con F tenía 28/47; con `c_high` 0,84, 28/47; contando autos vivos distintos, 25/47.
   - La causa es el pool: la mediana de su d guardado es 22,7 %, y 38 de sus 47 matches están entre 5 y 35 % debajo.
   - En el conjunto actual hay 4 búsquedas por encima del 25 %.
3. **Menos «🔥 Nueva oportunidad» por mail:** 32 → 22 en el conjunto actual.
   - No todas las que se van eran sospechosas: con F, 5 de las 17 🔥 de hoy que dejaban de serlo eran descuentos creíbles de 7–13 % que pasaban a «buena».
   - Se pierden los extras que solo van con 🔥 (seguimiento de precio PAR-03, costo total PAR-01, mensaje PRO-01).
4. **Precisión de la voz de agencia.** Con la versión medida, al menos 38 de 545 disparos (7 %, hasta 10 %) eran particulares con «services en concesionario oficial», y 4 eran negaciones. La versión final saca esa rama y pide voz en plural, pero su precisión no está medida.
   - No cambia ninguna alerta actual: los 2 topes son 264835 y 157823, ambos con voz real de agencia.
   - Es un riesgo para las búsquedas con preferencia de vendedor, que se vigilan en la sombra.
5. **El vendedor «confirmado» de FB es una heurística** (`"concesionaria" in joined` sobre toda la ficha). Con F un error costaba 0,4 en el promedio; con el tope tapa la alerta. No está medido.
6. **La referencia es la guardada, no la de decisión.** Cerca de los cortes de 5/35/50 % el backtest es incierto en ±15 %. §4.4 lo corrige para la próxima medición.
7. **Juicio, no ajuste.** El 0,9 por pool de nivel modelo, el 0,3 sin año, el −9 de Kavak, el 2,5 del spread, el ±2 % y el 0,82 salen de criterio, con sensibilidad medida. Conviene revisarlos cada mes; el de Kavak, con la consulta de celdas.
8. **Etiquetas escasas.** Hay 3 positivos y 1 par positivo/negativo, y ese par queda invertido. El volumen de alertas no está validado por ningún clic.
9. **La correlación positiva es débil** en el conjunto actual (+0,03 a +0,05), y el sesgo ARS/USD sigue sin explicar: un auto en USD a su precio típico queda ~12 % «caro».
10. **Datos vivos.** Las cifras se mueven entre corridas. Toda comparación de este documento es de una misma consulta.

## 14. Decisiones para Juan

Seis decisiones, cada una con la pregunta, las opciones, la recomendación y qué cambia en las búsquedas actuales. Las que **revisan una decisión que Juan ya tomó** están marcadas con ⚠️.

### Decisión 1. ¿Qué es «🔥 Oportunidad» y cómo se arma el score? ⚠️

- **Pregunta.** ¿Adoptar «precio × encaje» (§3) como la definición de 🔥 y de los cuatro niveles?
- **Revisa:**
  - **PAR-02 tramo 1 (29–30/10)**, «no topear en buena desde 35 %», y el tope del Apéndice A (50–65 % topeado en «buena»). Pasan a: desde 35 % como mucho «buena» con «verificá», y desde 50 % como mucho «coincidencia». Por qué:
    - más allá de 40 % bajan los clics salientes;
    - 3 de los 4 descartes explícitos estaban entre 33 y 59 %;
    - hoy hay 14 🔥 por encima de 35 %.
  - **Los pesos de TECHNICAL_PLAN §6.3 y del Apéndice A.** km (15), completitud (5) y antigüedad (10) salen del score, y la versión pasa a ser una preferencia.
  - **La magnitud de PRO-01 opción C (02/11).** Un vendedor sin dato con el filtro estricto sigue pasando y se ve «vendedor sin dato», pero resta −0,03 en vez de −0,15 y no puede ser 🔥.
- **Opciones:**
  - (a) F2;
  - (b) F, la propuesta anterior: falla los criterios 1 y 3 en el extendido;
  - (c) seguir con la fórmula de hoy.
- **Recomendación: (a).**
- **Qué cambia hoy** (conjunto actual):
  - alertas 111 → 103 y alertas 🔥 32 → 22;
  - alertas malas a «buena» o más 14 → 0, y 0 alertas creíbles perdidas al decidir;
  - 🔥 en la lista 132 → 356;
  - búsquedas con 6 o más restricciones y 🔥: 0 → 5 de 12;
  - el test del ejemplo del PRD sigue en 85–90.

### Decisión 2. El vendedor: tope y voz de agencia ⚠️

- **Pregunta.** Si el vendedor confirmado es distinto del que pide la preferencia (o un «particular» escribe como agencia), ¿hasta dónde puede llegar el aviso?
- **Revisa:**
  - **PRO-01 (02/11), en la práctica.** El filtro estricto de vendedor es Pro y el resto de los planes lo usa «como preferencia». Con el tope, la preferencia gratuita frena las alertas a «buena» o más casi igual que el estricto. Lo único que le queda al Pro es que el auto no se liste.
  - **DESCRIPTION_INTELLIGENCE («la descripción no ajusta la mediana ni el score»).** Es la primera vez que el texto de la descripción mueve un nivel.
  - **El principio de `seller.py`** («todo consumidor lee el vendedor de acá»): la voz de agencia vive en un predicado aparte.
- **Opciones del tope:**
  - (a) como mucho «coincidencia»;
  - (b) como mucho «buena»: las dos publicaciones de agencia de la Corsa 97 volverían a alertar como «buena» (no medido);
  - (c) tope solo con el filtro Pro: hoy no lo usa nadie, así que la 97 volvería a recibir esas dos alertas.
- **Opciones de la voz de agencia:**
  - (a) cuenta como posible agencia para la preferencia, con la frase visible en la ficha («posible agencia por la descripción: «…»»), pero no para el filtro estricto;
  - (b) solo como señal PAR-02 («conviene preguntar si es titular»), sin tocar el nivel;
  - (c) además, aplicarla al filtro estricto «solo particulares».
- **Recomendación: tope (a) y voz de agencia (a), con la regex acotada de §3.2.** Es coherente con lo que hizo el usuario que pagó: sus dos descartes por vendedor eran agencias de FB.
- **Qué cambia hoy:**
  - Afecta a 4 búsquedas, 3 del usuario que pagó.
  - La Corsa 97 se queda sin su única alerta (264835, que con F era 🔥). Con la voz de agencia (b), la recupera.
  - Las dos publicaciones de agencia de la 97 siguen sin alertar.
  - La Clio 372908 pasa a «coincidencia» y le llega igual, porque la 95 avisa desde «todo».
  - Con (c), un «particular» con voz de agencia deja de matchear en una búsqueda Pro estricta. Hoy no hay ninguna.

### Decisión 3. Datos que no son lo que dicen: relleno, «Sold» y pools

- **Pregunta.** ¿Cómo se tratan el precio de relleno y los avisos vendidos?
- **Opciones del precio de relleno:**
  - (a) bandera que solo lee f3: como sin precio y como mucho «coincidencia», solo para los avisos que ya matchean con su precio publicado, con dígitos 1–8;
  - (b) excluirlos como un anticipo.
- **Opciones de los pools:**
  - (i) los avisos de relleno siguen en los pools;
  - (ii) salen, con una migración en el paso a real, después de medir cuánto mueven las medianas.
- **Opciones de «Sold ·»:**
  - (a) arreglo del colector ya y aparte (§4.6), con «Pending/Pendiente» incluidos y los vendidos dentro de los pools como cualquier `gone`;
  - (b) esperar al PR de f3.
- **Recomendación:** relleno (a), pools (ii) medidos en la sombra, «Sold» (a). La regla «mismo precio en 3 autos» se saca (§3.5).
- **Qué cambia hoy:**
  - En el conjunto actual no cambia ninguna alerta.
  - En el extendido, F2 bloquea al decidir las 6 alertas del Golf a 11.111 (búsquedas 93, 148 y 266).
  - En las listas, se van las 12 🔥 basura de F: 5 de relleno en la 382 y 7 «Sold».
  - El arreglo del colector pasa ya a `gone` los 56 avisos de FB «Sold/Vendido» que hoy figuran activos, y los saca de la pestaña y del dashboard. No cambia ninguna decisión de alerta.

### Decisión 4. Kavak −9 y el umbral Pro ⚠️

- **Pregunta.** ¿Kavak se compara con su ajuste de −9 también para el umbral Pro, y qué número ve la persona?
- **Revisa:**
  - **El umbral Pro del 14/10** (PLANES §3.2: «alerta al instante con `diff_pct ≥ X`»);
  - la lista de «se mantienen sin cambios» del spec de F, que incluía el umbral Pro por `diff_pct`.
- **Opciones:**
  - (a) −9 en el score y en el umbral Pro (un solo número, `deal_d`), con el crudo visible y la aclaración de Kavak;
  - (b) −9 solo en el score, con el umbral Pro en el crudo;
  - (c) sin −9.
- **Recomendación: (a).**
  - El −9 está medido como el mismo auto (0,891).
  - Con (b), un Pro con umbral de 10 % recibe al instante un Kavak que el score llama «en línea».
  - El supuesto de que el resto se negocia ~9 % no está medido, y por eso se recalcula cada mes.
- **Qué cambia hoy:**
  - Ninguna alerta, porque ninguna búsqueda tiene umbral Pro.
  - En el extendido, las 6 alertas de Kavak a su precio típico siguen sin salir.
  - Con (c), +15 alertas 🔥 de Kavak.

### Decisión 5. Lo que ve la persona fuera del score

- **Pregunta.** ¿Se adoptan juntos estos cambios de consumo?
  - Los mails cuentan ofertas creíbles vivas y sin duplicados (§6).
  - Las alertas repetidas del mismo auto se pliegan (§4.3).
  - La pestaña agrupa duplicados y el dashboard cuenta solo 🔥 frescas.
  - Se suma el orden «Año más nuevo».
  - El PRD:187 y la landing pasan a «11 % debajo de 23 publicaciones similares».
- **Opciones:**
  - (a) todo junto, en el paso a real;
  - (b) por partes;
  - (c) solo el score.
- **Recomendación: (a).** Más adelante, después de la sombra, una preferencia «preferir más nuevo dentro del rango».
- **Qué cambia hoy:**
  - el conteo «por debajo» pasa de 39 a 589 (usuario que pagó: Gol 4, Clio 1, Corsa 2);
  - las alertas sin duplicados pasan de 103 a 99;
  - la pestaña muestra 294 🔥 vivas (273 autos distintos) en vez de 124.
  - Para el usuario que pagó (pase hasta ~28/11), además: ¿le mandamos a mano el aviso de 409916?

### Decisión 6. Despliegue y criterios de la sombra ⚠️

- **Pregunta.** ¿Sombra de 10–14 días con los criterios de §11, y un solo bump después?
- **Revisa** la regla de que los criterios se fijan antes de empezar: los criterios 1 y 2 se reformularon después de verlos fallar sobre estas mismas búsquedas. Se puede, si Juan los congela ahora, antes de la sombra.
- **Opciones de los criterios:**
  - (a) los de §11 tal como están: «creíble al decidir», leído de `match_decisions`;
  - (b) los del spec de F: con ellos, F2 falla el criterio 1 por los Kavak y por la basura.
- **Opciones para el criterio 6, que sigue abierto:**
  - (a) contar 🔥 vivas y autos distintos en búsquedas con 30 o más matches: la 307 sigue en 53 %;
  - (b) `c_high` 0,84: arregla la 366 (7/22) y la 344, pero la 307 queda en 60 %, y las alertas 🔥 del extendido caen a 151/262 = 0,58, así que falla el criterio 3;
  - (c) convertirlo en una lista para revisar el pool, sin bloquear.
- **Recomendación: criterios (a); para el 6, (c), contando 🔥 vivas y autos distintos.** Ninguna salida arregla la 307, y su causa es el pool de comparables, que está fuera de este cambio.
- **Opciones de despliegue:**
  - (a) sombra y después un bump;
  - (b) directo.
- **Recomendación: (a).** No conviene un puente por config mientras tanto. La regla vigente («aprobación de todo cambio que mueva scores») cubre todo este documento.
- **Qué cambia hoy:** durante la sombra, nada. Solo sale el arreglo de «Sold» si se aprueba en la decisión 3.

### Parámetros (se ajustan en sombra)

- **Cómo se usan.** Se congelan al empezar la sombra. Si hay que moverlos, se mueven por config y la medición vuelve a empezar desde ese día.
- **De dónde sale la sensibilidad.** Del conjunto extendido de frescos, con F2 completo, salvo donde dice «actual» o «medido con F».

| parámetro | valor | qué hace | sensibilidad medida |
|---|---|---|---|
| `x_high` | 0,70 | piso de precio para 🔥 | 0,65: 355 🔥 en listas (actual) · 0,75: 140 alertas 🔥 y 305 🔥 en listas (actual) |
| `y_high` | 0,70 | piso de encaje para 🔥 | 0,60 (medido con F): +8 🔥, 9 de otra versión |
| `c_high` | 0,82 | mínimo combinado de 🔥; inicio de la banda 85–99 | 0,80: 175 alertas 🔥 y 362 🔥 en listas (actual) · 0,84: 151 y 319 |
| `x_good` · `y_deal` | 0,65 · 0,45 | «buen precio» | `y_deal` 0,40: 834 alertas · 0,50: 831; las perdidas no cambian |
| `y_good` · `fair_min_d` | 0,85 · −2 | «coincide, precio en línea» | medido con F: −5 da 110 alertas en el actual, 20 sobre la mediana; 0 da 93 |
| `fit.unknown` | 0,75 | preferencia sin dato | 0,60: 164 alertas 🔥 (−9) |
| `fit.unknown_hard` | 0,03, solo en el score | filtro duro sin dato | si decide el nivel, como en F: 33 perdidas y tarjeta≠detalle 56 |
| `fit.fail` · `fit.trim_other` | 0,4 · 0,5 | preferencia fallida · otra versión | `trim_other` 0,55 sin la regla 1: 7 perdidas, tarjeta≠detalle 24 |
| `d_mult` · `d_floor` · `d_ceil` | 2,5 · 12 · 20 | dónde se llega al crédito completo | medido con F: `d_mult` 2,0 da 375 🔥 y 5 búsquedas con más de 25 % |
| `cred_max` · `d_susp` · exclusión | 35 · 50 · 65 | banda creíble, sospecha y exclusión | medido con F: `cred_max` 28 baja las alertas 🔥 de 22 a 12 (actual) |
| `n_min_high` | 10 | comparables mínimos para 🔥 | – |
| `r_model` · `r_noyear` | 0,9 · 0,3 | confiabilidad por pool de modelo y sin año | – |
| `kavak_offset` | 9 | sesgo de Kavak | 6: 837 alertas, 179 🔥, 12 perdidas · 12: 822, 173, 22 · 0: +15 alertas 🔥 de Kavak |
| tope de vendedor | sí | §3.3 | sin él: 835 alertas, y vuelven 157823, 170382, 264835 y 372908 como «buena» |
| precio de relleno | dígitos 1–8, 4 o más | §3.5 | sin la regla: 837 alertas, 179 🔥 (+6 del Golf) |
| voz de agencia | sí | §3.2 | sin la regla: 832 alertas, 174 🔥 (+264835) |
| barrido de la espera | 20 min | §4.1 | 10 min: 170382 alerta como «buena» |
| `rescore.every_hours` | 24 | §5 | – |
| ventana del dedupe | 30 días | §4.3 | – |

**Se mantienen sin cambios:**
- «los gone cuentan» en comparables, incluidos los vendidos;
- F-02 («posible agencia» = agencia);
- «ninguna señal PAR-02 mueve el score», con sus bandas de copy (25/35/50);
- la exclusión a partir de 65 %;
- el tope diario y la cuota de prueba.

## 15. Anexos

- [`2026-11-08-recalibracion-score-por-busqueda.md`](2026-11-08-recalibracion-score-por-busqueda.md):
  - las 77 búsquedas actuales a las 22:55 y las 6 pruebas que vencieron en el día;
  - hoy, F y F2 en la misma consulta, con los motivos de cada alerta perdida o ganada;
  - el usuario que pagó, aviso por aviso.
- [`2026-11-08-recalibracion-score-f2.sql`](2026-11-08-recalibracion-score-f2.sql): la CTE del backtest con la que se midió F2, con las diferencias contra la versión final en su encabezado.
- **Lo que no se sube al repo:** el prefijo del backtest, las consultas de cada corrida y sus resultados crudos quedaron en el espacio de trabajo del análisis.

## 16. Verificación

**Qué se verificó:**
- **Números.** Una verificación adversarial volvió a correr F2 de cero el 2026-11-08, entre las 22:24 y las 22:47 UTC, con tails propios, el SQL entregado y la fila de F. Todo fue solo lectura.
  - Extendido de frescos: exacto, alerta por alerta y búsqueda por búsqueda.
  - Conjunto actual: dentro de la deriva de los datos vivos.
  - Mitades: replicadas. Los 23 matches del usuario que pagó: mismos scores y niveles.
- **Diseño.** Otra verificación leyó el código que toca cada regla y corrió 11 SELECT, para ver si cada regla se puede calcular con lo que el worker tiene al decidir, dónde va y qué decisión de Juan toca.
- **Por búsqueda.** La corrida del anexo (22:55–23:01) volvió a dar, en las búsquedas actuales a esa hora, 0 alertas creíbles perdidas al decidir.

**Qué cambió por la verificación** (ya incorporado arriba):
1. **🔥 basura de hoy en el conjunto actual: 1, no 0.**
2. **Criterio 3 contra 🔥 creíbles en el conjunto actual: 22/20 = 1,10.**
3. **Criterio 6.** Las búsquedas por encima del 40 % en el extendido son la 307 y la 366, y ninguna salida propuesta arregla la 307 (decisión 6).
4. **«Sold» era información del futuro.** Sale del score y pasa al colector (§4.6). Ninguna alerta enviada tenía ese título al decidir, así que la «pérdida» de la 350 y el silencio de la 89 eran artefactos. Además:
   - FB sí pasa avisos a `gone`;
   - un vendido no sale de los pools, por «los gone cuentan».
5. **«Al decidir: 0 empeoran» no contaba los silencios.** Contándolos: 43/91/37/10 en el extendido y 5/53/8/2 en el actual.
6. **La correlación es frágil:** en el conjunto actual bajó de +0,053 a +0,026 en una hora.
7. **Cambios de diseño:**
   - precio de relleno solo con dígitos 1–8 y como bandera, no como precio null;
   - sin la regla «mismo precio en FB»;
   - regex de agencia sin «concesionario oficial» y con voz en plural, fuera de `effective_seller`;
   - banda 🔥 anclada en `c_high`;
   - Kavak con el número crudo visible;
   - criterio 1 leído de `match_decisions`.
8. **Decisiones de Juan que F2 tocaba sin marcarlo:** PRO-01, el umbral Pro del 14/10 y DESCRIPTION_INTELLIGENCE. Ahora están en las decisiones 2 y 4.
