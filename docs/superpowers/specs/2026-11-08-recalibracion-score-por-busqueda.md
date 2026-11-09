# Recalibración del score · resultado búsqueda por búsqueda (F2)

Anexo de [`2026-11-08-recalibracion-score-design.md`](2026-11-08-recalibracion-score-design.md). Fecha: 2026-11-08. Corrida por búsqueda a las 22:55 y 22:58 UTC (dos mitades por paridad de `search_id`) y a las 23:01 (las 6 pruebas que vencieron en el día). Todo con SELECT de solo lectura en producción; las únicas funciones llamadas fueron las STABLE `plan_limits_for` y `search_access_active`. Hoy, F y F2 se calcularon **en la misma consulta**.

**Qué se compara.**
- **Hoy** = la fórmula actual con los datos de la tarjeta (`cur@card`), que es la que decide las alertas.
- **F** = la propuesta anterior en su punto de decisión.
- **F2** = la propuesta final en su punto de decisión: tarjeta, salvo las búsquedas con preferencia de vendedor cuya tarjeta no trae vendedor, que esperan al detalle. Es la versión medida del [anexo SQL](2026-11-08-recalibracion-score-f2.sql). Las diferencias con la versión final del spec no cambian ninguna alerta de esta tabla salvo una: la 429256 de la búsqueda 350 (ver la nota de esa fila).

**Conjunto.** Las 77 búsquedas con acceso activo a las 22:55, sin admins: 74 pruebas de 72 h y las 3 del usuario que pagó (92, 95 y 97). 64 tienen matches y 38 tienen al menos un match fresco en la ventana de 30 días. Son 3.090 matches y 250 frescos. Al final van las 6 pruebas que vencieron entre la corrida del spec (21:38) y esta (310 a 315).

**Por qué los totales no son los de §9 del spec.** Los datos están vivos: entre las 21:38 y las 22:55 vencieron 6 pruebas (310–315), se crearon 4 búsquedas (390–393) y entraron matches nuevos. Sumando las 77 actuales y las 6 vencidas, las alertas dan 113 → 109 → 107 (hoy → F → F2); en el spec, a las 21:38, eran 111 → 105 → 103. Las comparaciones valen dentro de cada corrida.

## Resumen

**Lo que le llega al usuario** (alertas inmediatas posibles, antes del tope diario y de la cuota de prueba), en las 77 búsquedas actuales: **103 → 97 → 95**. Sin duplicados: 99 → 93 → 91.

| resultado de F2 por búsqueda | búsquedas | cuáles | por qué |
|---|---|---|---|
| mejora | 5 | 92 (usuario que pagó), 341, 358, 366, 372 | 92 y 358 pasan de 0 alertas a 1 o más; 92 recibe el auto que se perdió (409916). 341, 366 y 372 suman una alerta «en línea con el mercado». |
| igual | 64 | 51 con matches y 13 sin matches | El mismo número de alertas. En muchas cambian las 🔥 de la lista (columna 🔥 lista). |
| menos ruido | 6 | 329, 334, 338, 342, 350, 357 | Pierden **solo** alertas no creíbles: 8 avisos de FB sin año o a 50 % o más debajo, 2 sin precio, 2 de la 334 (que avisa desde «coincidencia») a 31 % y 54 % **arriba** de la mediana, y 1 ML con 6 comparables. La 350 pierde además la 429256 por el título «Sold» de hoy, que al decidir no tenía (ver la fila). |
| silencio | 2 | 345, 371 | Su única alerta era débil: 345, un aviso de rosariogarage sin precio; 371, un ML a 5 % debajo con menos de 10 comparables. Las dos están en la lista de silencios aceptables del criterio 2 (§11 del spec). F las silencia igual. |
| pierde una alerta creíble al decidir | **0** | – | – |

- **F2 contra F, búsqueda por búsqueda.** Las alertas cambian en dos búsquedas:
  - en la 97, F mandaba la 🔥 264835 y F2 no (voz de agencia en la descripción);
  - en la 350, F2 no manda la 429256 «Sold» (artefacto, ver la fila).
  - Las 🔥 alertadas cambian además en la 329 (0 → 1) y la 334 (1 → 2) por la 🔥 combinada.
- **Búsquedas con matches frescos y ninguna alerta:** 13 → 12 → 13 de 38.
- **La lista y la pestaña «Oportunidades» (🔥):** 130 → 324 → **344**, de las cuales 343 son ofertas creíbles (hoy 76 de 130). Vivas (aviso activo y sin «Sold»): 122 → 260 → 281. Vivas y autos distintos: 118 → 234 → 260.
  - 21 búsquedas pasan de 0 🔥 creíbles a 1 o más.
  - 16 búsquedas tenían 🔥 sospechosas hoy y dejan de mostrarlas. 339, 377 y 384 se quedan sin 🔥.
  - Los mayores aumentos son casi todos de backfill y no alertan: 382 (0 → 59), 341 (11 → 44), 323 (12 → 29) y 365 (2 → 22).
- **Concentración.** Con 20 o más matches, superan el 25 % de 🔥: 1 → 3 → 4 búsquedas (334, 344, 365 y 366). Supera el 40 % solo la **366** (9 de 22, todas creíbles): es el criterio 6 del spec, que sigue abierto.
- **Muchos filtros.** Tienen al menos una 🔥 4 de las 11 búsquedas con 6 o más filtros y preferencias (hoy 0).
- **El conteo «por debajo de comparables» de los mails** (columna «Por debajo»).
  - Hoy cuenta las 🔥 guardadas, que ya decayeron: 39 matches en 15 búsquedas.
  - Con la definición propuesta son 589 en 47 búsquedas. Es la primera medición con la definición completa: oferta creíble (5–35 % debajo con el −9 de Kavak, 10 o más comparables, con año, precio que no es de relleno), aviso vivo y sin duplicados.
  - Para el usuario que pagó: Gol 0 → 4, Clio 0 → 1, Corsa 0 → 2.

**Cómo se clasificó.**
- **Mejora:** gana alertas o alertas creíbles, sin perder ninguna creíble.
- **Menos ruido:** pierde alertas y ninguna era creíble.
- **Silencio:** queda sin alertas; se revisa con el criterio 2.
- **Empeora:** pierde una alerta creíble al decidir. Creíble al decidir = precio de la tarjeta entre 5 % y 35 % debajo (con el −9 de Kavak), 10 o más comparables, año conocido, precio que no es de relleno y aviso vivo.
- Con la definición del harness (el `diff_pct` guardado), la 350 contaría como «empeora» por la 429256. Por eso lleva un asterisco.
- Para las 🔥 de F2, que sean creíbles es cierto casi por construcción: en la lista eso mide que la regla hace lo que dice, no que la regla sea buena.

## Tabla de las 77 búsquedas actuales

Orden: matches frescos de mayor a menor, después total de matches.

Columnas:
- **Plan:** prueba = prueba gratis de 72 h; pase = Particular pago.
- **Avisa desde:** `notify_min_level` («todo» = `low`).
- **FB/ML %:** porcentaje de sus matches de Facebook y de MercadoLibre. El resto son rosariogarage, deruedas, autocosmos y Kavak.
- **Restr.:** filtros más preferencias.
- **Alertas:** hoy → F → **F2**; entre paréntesis, sin duplicados (solo si cambia).
- **🔥 alertas:** alertas «Nueva oportunidad».
- **🔥 lista:** 🔥 en la lista; entre paréntesis, cuántas de F2 siguen vivas (solo si cambia).
- **Por debajo (mail):** hoy (🔥 guardadas) → propuesto (ofertas creíbles vivas y sin duplicados).
- **Resultado:** de F2 contra hoy.

| Búsq. | Plan | Avisa desde | FB/ML % | Restr. | Matches | Frescos | Alertas | 🔥 alertas | 🔥 lista | Por debajo (mail) | Resultado | Nota |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 341 | prueba | buena | 38/51 | 4 | 255 | 33 | 19 → 20 → **20** (15 → 16 → 16) | 7 → 4 → **4** | 11 → 45 → **44** (40 vivas) | 2 → 81 | mejora | gana 416388 ML 2 % arriba (buena); siguen alertando con otro nivel: 415100 🔥 → buena, 417403 🔥 → buena, 497197 🔥 → buena; 5 🔥 sospechosas de hoy dejan de serlo |
| 350\* | prueba | buena | 9/14 | 1 | 221 | 33 | 14 → 13 → **12** | 7 → 3 → **2** | 62 → 35 → **37** (36 vivas) | 11 → 53 | menos ruido* | pierde 429256 FB 33 % debajo (título «Sold» de hoy; queda buena); 472810 FB 50 % debajo (sin año; queda coincidencia); 490156 FB 52 % debajo (sin año; queda coincidencia); gana 490500 ML en la mediana (buena); siguen alertando con otro nivel: 420507 🔥 → buena, 421029 🔥 → buena, 485282 🔥 → buena, 494527 🔥 → buena; 19 🔥 sospechosas de hoy dejan de serlo; con F: 13 alertas, 3 🔥 |
| 323 | prueba | buena | 16/74 | 3 | 383 | 31 | 11 → 11 → **11** | 4 → 4 → **4** | 12 → 23 → **29** (24 vivas) | 0 → 42 | igual | 4 🔥 sospechosas de hoy dejan de serlo |
| 329 | prueba | buena | 54/23 | 1 | 103 | 28 | 11 → 6 → **6** | 5 → 0 → **1** | 11 → 14 → **16** | 3 → 20 | menos ruido | pierde 447823 FB (sin precio; queda coincidencia); 459024 FB (sin precio; queda coincidencia); 461925 FB 61 % debajo (sin año; queda coincidencia); 490273 FB 42 % debajo (sin año; queda coincidencia); 495237 FB 50 % debajo (≥ 50 % debajo; queda coincidencia); 495970 FB 25 % debajo (sin año; queda coincidencia); gana 403994 deruedas en la mediana (buena); siguen alertando con otro nivel: 410607 🔥 → buena, 414082 🔥 → buena; 7 🔥 sospechosas de hoy dejan de serlo; con F: 6 alertas, 0 🔥 |
| 342 | prueba | buena | 61/17 | 3 | 18 | 10 | 3 → 2 → **2** | 0 → 1 → **1** | 0 → 3 → **1** | 0 → 3 | menos ruido | pierde 472806 FB 50 % debajo (sin año; queda coincidencia); siguen alertando con otro nivel: 458976 buena → 🔥 |
| 357 | prueba | buena | 7/75 | 2 | 151 | 9 | 5 → 4 → **4** | 1 → 1 → **1** | 1 → 3 → **3** (1 viva) | 1 → 25 | menos ruido | pierde 429838 ML 4 % debajo (menos de 10 comparables; queda coincidencia) |
| 97 | pase **(usuario que pagó)** | buena | 100/0 | 8 | 9 | 9 | 0 → 1 → **0** | 0 → 1 → **0** | 0 → 1 → **0** | 0 → 2 | igual | 264835 (FB 2008 26 % debajo, «particular» con voz de agencia) queda coincidencia y no alerta; con F era 🔥. Los dos avisos de agencia (157823 y 170382) siguen sin alertar |
| 328 | prueba | buena | 18/27 | 4 | 98 | 8 | 5 → 5 → **5** | 0 → 1 → **1** | 0 → 18 → **14** (12 vivas) | 0 → 34 | igual | siguen alertando con otro nivel: 398019 buena → 🔥 |
| 334 | prueba | coinc. | 24/37 | 3 | 49 | 7 | 7 → 5 → **5** | 2 → 1 → **2** | 5 → 13 → **14** | 0 → 13 | menos ruido | pierde 406739 ML 31 % arriba (más de 2 % sobre la mediana; queda baja); 417389 ML 54 % arriba (menos de 10 comparables; queda baja); 2 🔥 sospechosas de hoy dejan de serlo; 🔥 = 29 % de sus matches; con F: 5 alertas, 1 🔥 |
| 372 | prueba | buena | 6/56 | 1 | 36 | 7 | 4 → 5 → **5** | 1 → 1 → **1** | 1 → 3 → **3** | 1 → 5 | mejora | gana 471820 ML 1 % arriba (buena) |
| 358 | prueba | buena | 27/60 | 4 | 176 | 6 | 0 → 2 → **2** | 0 → 0 → **0** | 4 → 9 → **12** | 0 → 18 | mejora | gana 443217 FB 4 % debajo (buena) y 470031 ML (buena: con 2 comparables no hay referencia de precio y encaja con lo pedido); 1 🔥 sospechosa de hoy deja de serlo |
| 367 | prueba | buena | 35/5 | 3 | 111 | 5 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 17 | igual | sin cambios en alertas |
| 338 | prueba | buena | 80/10 | 4 | 41 | 5 | 3 → 2 → **2** | 0 → 0 → **0** | 0 → 2 → **1** | 0 → 7 | menos ruido | pierde 413946 FB 55 % debajo (sin año; queda coincidencia) |
| 319 | prueba | buena | 0/100 | 7 | 5 | 5 | 1 → 1 → **1** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 | igual | sin cambios en alertas |
| 344 | prueba | buena | 13/17 | 3 | 47 | 4 | 3 → 3 → **3** | 0 → 2 → **2** | 0 → 16 → **18** (15 vivas) | 0 → 17 | igual | siguen alertando con otro nivel: 414059 buena → 🔥, 414060 buena → 🔥; 🔥 = 38 % de sus matches |
| 331 | prueba | buena | 100/0 | 4 | 11 | 4 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 381 | prueba | buena | 48/12 | 4 | 145 | 3 | 1 → 1 → **1** | 0 → 0 → **0** | 0 → 9 → **8** (7 vivas) | 0 → 35 | igual | sin cambios en alertas |
| 354 | prueba | buena | 3/3 | 5 | 69 | 3 | 1 → 1 → **1** | 0 → 0 → **0** | 0 → 5 → **5** (4 vivas) | 0 → 6 | igual | sin cambios en alertas |
| 374 | prueba | buena | 10/31 | 4 | 39 | 3 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 3 → **0** | 0 → 6 | igual | sin cambios en alertas |
| 366 | prueba | buena | 32/64 | 5 | 22 | 3 | 1 → 2 → **2** | 0 → 1 → **1** | 0 → 7 → **9** | 1 → 13 | mejora | falla el criterio 6: 9 🔥 de 22 matches (41 %), todas creíbles y casi todas de backfill; gana 498760 ML 1 % arriba (buena); siguen alertando con otro nivel: 494838 buena → 🔥 |
| 92 | pase **(usuario que pagó)** | buena | 80/10 | 8 | 10 | 3 | 0 → 1 → **1** | 0 → 0 → **0** | 0 → 3 → **3** | 0 → 4 | mejora | gana 409916 FB 2012 47 % debajo (buena, «verificá»): el auto que se había perdido. Ver «Usuario que pagó» |
| 360 | prueba | buena | 40/20 | 4 | 5 | 3 | 3 → 3 → **3** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 3 | igual | sin cambios en alertas |
| 371 | prueba | buena | 4/79 | 4 | 92 | 2 | 1 → 0 → **0** | 0 → 0 → **0** | 0 → 1 → **1** | 0 → 21 | silencio | su única alerta era 495419 ML 5 % debajo con menos de 10 comparables: silencio aceptado por el criterio 2 |
| 364 | prueba | buena | 27/46 | 3 | 63 | 2 | 2 → 2 → **2** | 1 → 1 → **1** | 4 → 8 → **10** (7 vivas) | 4 → 12 | igual | 3 🔥 sospechosas de hoy dejan de serlo |
| 345 | prueba | buena | 18/34 | 2 | 38 | 2 | 1 → 0 → **0** | 0 → 0 → **0** | 0 → 2 → **2** (1 viva) | 0 → 3 | silencio | su única alerta era 413987 rosariogarage sin precio: silencio aceptado por el criterio 2 |
| 321 | prueba | buena | 31/63 | 8 | 32 | 2 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 2 → **4** (1 viva) | 0 → 8 | igual | sin cambios en alertas |
| 363 | prueba | buena | 48/45 | 5 | 31 | 2 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 3 | igual | sin cambios en alertas |
| 318 | prueba | buena | 0/66 | 5 | 29 | 2 | 1 → 1 → **1** | 1 → 0 → **0** | 2 → 5 → **7** (6 vivas) | 1 → 9 | igual | siguen alertando con otro nivel: 495416 🔥 → buena; 1 🔥 sospechosa de hoy deja de serlo |
| 384 | prueba | buena | 12/40 | 4 | 25 | 2 | 0 → 0 → **0** | 0 → 0 → **0** | 1 → 1 → **0** | 1 → 1 | igual | 1 🔥 sospechosa de hoy deja de serlo |
| 339 | prueba | buena | 19/25 | 3 | 16 | 2 | 1 → 1 → **1** | 1 → 0 → **0** | 2 → 1 → **0** | 2 → 2 | igual | siguen alertando con otro nivel: 486247 🔥 → buena; 2 🔥 sospechosas de hoy dejan de serlo |
| 320 | prueba | buena | 42/25 | 8 | 12 | 2 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 2 | igual | sin cambios en alertas |
| 340 | prueba | buena | 27/27 | 3 | 11 | 2 | 1 → 1 → **1** | 1 → 0 → **0** | 3 → 1 → **1** | 3 → 1 | igual | siguen alertando con otro nivel: 486249 🔥 → buena; 3 🔥 sospechosas de hoy dejan de serlo |
| 336 | prueba | buena | 88/0 | 6 | 8 | 2 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 95 | pase **(usuario que pagó)** | todo | 50/50 | 9 | 4 | 2 | 2 → 2 → **2** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 | igual | las mismas 2 alertas de hoy; 372908 (agencia de ML, 29 % debajo) queda coincidencia por el tope de vendedor (con F era buena) y le llega igual, porque avisa desde «todo» |
| 365 | prueba | buena | 38/34 | 2 | 80 | 1 | 0 → 0 → **0** | 0 → 0 → **0** | 2 → 19 → **22** (14 vivas) | 2 → 26 | igual | 1 🔥 sospechosa de hoy deja de serlo; 🔥 = 28 % de sus matches |
| 362 | prueba | buena | 63/13 | 4 | 16 | 1 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 3 → **3** | 0 → 3 | igual | sin cambios en alertas |
| 377 | prueba | buena | 0/63 | 3 | 8 | 1 | 1 → 1 → **1** | 1 → 0 → **0** | 1 → 0 → **0** | 0 → 0 | igual | siguen alertando con otro nivel: 481168 🔥 → buena; 1 🔥 sospechosa de hoy deja de serlo |
| 346 | prueba | buena | 0/100 | 2 | 4 | 1 | 1 → 1 → **1** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 382 | prueba | buena | 28/6 | 2 | 358 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 55 → **59** (36 vivas) | 0 → 58 | igual | todas las 🔥 son de backfill (0 frescos) |
| 391 | prueba | buena | 77/5 | 4 | 56 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 2 → **1** | 0 → 10 | igual | sin cambios en alertas |
| 386 | prueba | buena | 66/9 | 4 | 32 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 2 → 1 → **2** | 2 → 3 | igual | 1 🔥 sospechosa de hoy deja de serlo |
| 356 | prueba | buena | 4/44 | 3 | 27 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 3 → **5** (2 vivas) | 0 → 5 | igual | sin cambios en alertas |
| 335 | prueba | buena | 41/12 | 4 | 17 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 | igual | sin cambios en alertas |
| 337 | prueba | todo | 0/7 | 8 | 15 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **1** | 0 → 4 | igual | sin cambios en alertas |
| 355 | prueba | buena | 50/43 | 2 | 14 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 2 → 0 → **1** | 1 → 1 | igual | 1 🔥 sospechosa de hoy deja de serlo |
| 376 | prueba | buena | 36/36 | 4 | 14 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 2 → **2** | 0 → 2 | igual | sin cambios en alertas |
| 390 | prueba | buena | 17/83 | 6 | 12 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 → **1** | 0 → 3 | igual | sin cambios en alertas |
| 330 | prueba | buena | 0/91 | 3 | 11 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 380 | prueba | buena | 0/10 | 5 | 10 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 | igual | sin cambios en alertas |
| 378 | prueba | buena | 67/22 | 4 | 9 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 | igual | sin cambios en alertas |
| 388 | prueba | buena | 13/0 | 2 | 8 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 4 → 2 → **2** | 4 → 2 | igual | 2 🔥 sospechosas de hoy dejan de serlo |
| 349 | prueba | todo | 0/71 | 6 | 7 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 333 | prueba | buena | 0/0 | 2 | 5 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 → **1** (0 vivas) | 0 → 0 | igual | sin cambios en alertas |
| 373 | prueba | buena | 60/20 | 5 | 5 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 2 → **2** (1 viva) | 0 → 1 | igual | sin cambios en alertas |
| 316 | prueba | buena | 0/0 | 5 | 4 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 359 | prueba | buena | 0/0 | 3 | 3 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 322 | prueba | buena | 0/100 | 5 | 2 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 392 | prueba | buena | 0/100 | 2 | 2 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 326 | prueba | buena | 0/100 | 4 | 1 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 327 | prueba | buena | 0/100 | 4 | 1 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 343 | prueba | 🔥 | 0/100 | 1 | 1 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 375 | prueba | buena | 0/0 | 5 | 1 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 379 | prueba | buena | 0/0 | 3 | 1 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 383 | prueba | buena | 0/100 | 6 | 1 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |
| 317 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 324 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 325 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 332 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 351 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 352 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 361 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 368 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 369 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 370 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 385 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 389 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |
| 393 | prueba | buena | – | – | 0 | 0 | 0 | 0 | 0 | 0 → 0 | igual | sin matches |

\* 350: pierde 429256 solo porque hoy su título empieza con «Sold ·». Al decidir no lo tenía (las relecturas reescriben el título), así que en producción F2 la habría mandado como «buena». En la versión final, la regla «Sold» sale del score y pasa al colector (§4.6 del spec), y esta alerta vuelve. Lo que queda para la 350 es menos ruido: dos FB sin año a 50 % y 52 % debajo.

## Las 6 pruebas que vencieron en el día (310 a 315)

Estaban en la corrida del spec (21:38) y ya no tienen acceso a las 23:01. Se midieron con la misma consulta, limitada a esas 6 búsquedas.

| Búsq. | Plan | Avisa desde | FB/ML % | Restr. | Matches | Frescos | Alertas | 🔥 alertas | 🔥 lista | Por debajo (mail) | Resultado | Nota |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 315 | prueba | buena | 1/4 | 4 | 130 | 6 | 0 → 4 → **4** | 0 → 0 → **0** | 0 → 8 → **9** | 1 → 17 | mejora | gana 383978 deruedas 4 % debajo (buena); 444392 deruedas 3 % debajo (buena); 458835 FB 1 % arriba (buena); 498735 deruedas 2 % debajo (buena) |
| 314 | prueba | buena | 43/50 | 2 | 28 | 6 | 5 → 4 → **4** | 1 → 0 → **0** | 2 → 0 → **0** | 1 → 0 | menos ruido | pierde 413945 FB 55 % debajo (sin año; queda coincidencia); siguen alertando con otro nivel: 453884 🔥 → buena; 2 🔥 sospechosas de hoy dejan de serlo |
| 311 | prueba | buena | 8/58 | 5 | 12 | 4 | 3 → 3 → **3** | 0 → 1 → **1** | 1 → 2 → **2** | 0 → 5 | igual | siguen alertando con otro nivel: 400373 buena → 🔥 |
| 313 | prueba | buena | 50/17 | 6 | 6 | 3 | 2 → 1 → **1** | 0 → 1 → **1** | 0 → 2 → **2** | 0 → 2 | menos ruido | pierde 472802 FB 50 % debajo (sin año; queda coincidencia); siguen alertando con otro nivel: 458973 buena → 🔥 |
| 310 | prueba | buena | 100/0 | 2 | 7 | 1 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 1 | igual | sin cambios en alertas |
| 312 | prueba | buena | 100/0 | 3 | 1 | 0 | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 → **0** | 0 → 0 | igual | sin cambios en alertas |

- 315 mejora: despierta con 4 alertas «en línea» (deruedas y FB, entre 4 % debajo y 1 % arriba).
- 313 y 314 pierden solo un FB sin año a 50 % o 55 % debajo.
- 311 y 313 suben una alerta de «buena» a 🔥; 314 baja una de 🔥 a «buena».

## El usuario que pagó (pase Particular), aviso por aviso

Lo que recibió en 10 días:
- 2 alertas inmediatas, las dos de la Clio, a nivel `match`, porque esa búsqueda avisa desde «todo»;
- 0 alertas de Gol y Corsa, y 0 «🔥»;
- un mail de bienvenida que le dijo «encontramos 7, 0 por debajo de comparables», con los 7 Gol entre 21 % y 45 % debajo.

Los scores y niveles de esta sección salen de la corrida del spec (21:38). La verificación los reprodujo a las 22:25 en sus 23 matches, y la corrida de las 22:55 da las mismas alertas por búsqueda.

Columnas: hoy (`cur@card`) · F → **F2**, con «*» = alerta. «Diferida» = la decisión espera al detalle, porque la búsqueda prefiere particular y la tarjeta no trae vendedor.

### 92 · Gol 2007–2012, avisa desde «buena», 8 restricciones (preferencias: precio ideal 3.500, vendedor particular)

| match | aviso | % debajo (n) | hoy | F | **F2** | ¿alerta con F2? | lo que hizo él | lectura |
|---|---|---|---|---|---|---|---|---|
| 409916 | FB 2012, USD 3.236, fresco | 47 % (304) | 66 coincidencia | 80 buena* | **80 buena*** «muy por debajo: verificá todo antes de señar» | **sí**, diferida | – | Es el auto que se le había perdido. Sale como «buena» con la advertencia, no como 🔥: 47 % está en la banda de verificar. |
| 157183 | FB 2011, USD 3.215, backfill | 45 % (221) | 76 buena | 80 buena | 80 buena «verificá» | backfill | **guardó** | Bien. |
| 157184 | FB 2008, USD 3.859 | 22 % (112) | 55 | 93 🔥 | **89 🔥** | backfill | vio | Bien. La banda 🔥 ahora arranca en el 82 combinado. |
| 157188 | FB 2012, USD 3.896 | 35 % (179) | 60 | 93 🔥 | **89 🔥** | backfill | vio y salió al aviso | Bien. |
| 157185 | FB 2007, USD 3.226 | 33 % (105) | 56 | 96 🔥 | **93 🔥** | backfill | **descartó** | **Falla que queda:** sigue arriba del 2011 que guardó. El score no ve el estado del auto ni el año dentro de su rango. |
| 157186 | FB 2007, USD 2.913 | 40 % (105) | 56 | 82 buena | 82 buena «verificá» | backfill | **descartó** | Aceptable: está en la banda de verificar. |
| 157187 | ML 2008, USD 3.571 | 31 % (31) | 56 | 82 buena | 82 buena, «vendedor sin dato» | backfill | – | Sin vendedor no hay 🔥 en una búsqueda que pide particular. |
| 157189 | autocosmos 2009, USD 3.800 | 27 % (19) | 57 | 81 buena | 81 buena, «vendedor sin dato» | backfill | vio y salió al aviso | Igual que la anterior. |
| 384543 | FB sin año, USD 3.560, fresco | 37 % (713, todos los años) | 63 coincidencia | 63 | 63 coincidencia | no | – | Bien: sin año la comparación no vale. |
| 459473 | FB sin precio ni año, fresco | – | 46 baja | 55 | 55 coincidencia | no | – | Bien: nunca alerta a «buena». |

Alertas: 0 → 1 → **1**. 🔥 en la lista: 0 → 3 → **3**. «Por debajo» en los mails: 0 → **4**.

### 95 · Clio, avisa desde «todo», 9 restricciones (preferencias: 3.500, particular, 120.000 km)

| match | aviso | % debajo (n) | hoy | F | **F2** | ¿alerta con F2? | lectura |
|---|---|---|---|---|---|---|---|
| 296345 | FB 2013, USD 2.894, fresco; vendedor inferido como agencia (F-02) | 57 % (236) | 66 coincidencia* (la recibió) | 62 coincidencia* | **62 coincidencia*** «puede ser un anticipo» · «otro tipo de vendedor» | sí, como hoy | Sigue saliendo, ahora con el nivel y las advertencias correctas. |
| 372908 | ML 2012, USD 4.187, agencia, fresco | 29 % (18) | 63 coincidencia* (la recibió) | 80 buena* | **67 coincidencia*** | sí, como hoy | Tope de vendedor: es agencia y él pide particular. Le llega igual porque la búsqueda avisa desde «todo». |
| 158267 | ML 2013, USD 4.051, backfill | 40 % (24) | 63 | 82 buena | 82 buena «verificá» | backfill | – |
| 157572 | FB 2008, USD 2.251, backfill | 59 % (31) | 55 | 64 | 64 coincidencia, «puede ser un anticipo» | backfill | Bien: lo descartó. |

Alertas: 2 → 2 → **2**. «Por debajo»: 0 → **1**.

### 97 · Corsa, avisa desde «buena», 8 restricciones (preferencias: 3.500, particular); los 9 matches son frescos

| match | aviso | % debajo (n) | hoy | F | **F2** | ¿alerta con F2? | lectura |
|---|---|---|---|---|---|---|---|
| **264835** | FB 2008, USD 3.537, «particular» según FB | 26 % (129) | 64 coincidencia | **95 🔥*** | **68 coincidencia** | **no** | La descripción tiene voz de agencia («recibimos tu usado», «te lo compramos», «solo DNI + anticipo», «cuotas fijas»). Con la regla de voz de agencia cuenta como posible agencia y él pide particular. Sus dos descartes por vendedor eran agencias de FB. Sin esa regla vuelve a ser 🔥 (medido). Es la decisión 2 del spec. |
| 157823 · 170382 | FB 2009, USD 4.180, el mismo auto de agencia publicado dos veces | 14 % (133) | 61 · 65 coincidencia | 62 · 62 | **62 · 62 coincidencia** | no | Sin el tope de vendedor, la regla de datos faltantes las volvería a alertar como «buena». Con el tope, no. |
| 461912 · 495964 | FB sin año | 61 % y 25 % | 64 · 64 | 62 · 63 | 62 · 63 coincidencia | no | Bien. |
| 384867, 384868, 447805, 459006 | FB sin precio ni año | – | 45–46 baja | 55 | 55 coincidencia | no | Bien. |

Alertas: 0 → 1 → **0**. «Por debajo»: 0 → **2** (264835 y el auto de agencia, contado una vez).

**En síntesis, para el usuario que pagó:**
- **Lo que se arregla:**
  - el Gol recibe al decidir el auto creíble que le correspondía (409916, como «buena» con «verificá»);
  - lo sin precio, lo sin año, lo de 57–61 % debajo y las publicaciones de agencia no alertan a «buena»;
  - los mails dejan de decirle «0 por debajo».
- **Lo que no se arregla, o queda a decidir:**
  - La Corsa sigue sin alertas. Su única candidata, 264835, parece de agencia por la descripción. Que eso la saque es la decisión 2 del spec.
  - Su 2007 descartado (157185) queda 🔥 93, arriba del 2011 que guardó (80, «verificá»). Lo que separa sus guardados de sus descartados es el estado del auto y el año dentro del rango, y el score no ve ninguna de las dos cosas. La palanca propuesta es el orden «Año más nuevo» en la lista.

## Cómo se midió

- La consulta es el prefijo del backtest (una fila por match, con los datos de la tarjeta y del detalle) más la CTE del [anexo SQL](2026-11-08-recalibracion-score-f2.sql), con una fila de F. Es la misma armadura que usó la verificación de números.
- La clasificación y los motivos de cada alerta perdida o ganada salen de la misma consulta, alerta por alerta.
- «Por debajo (mail)» de hoy cuenta los `level = 'high'` guardados, que es lo que cuentan hoy los mails.
- Hoy, F y F2 comparten datos y momento. Los totales se mueven entre corridas por los datos vivos; las diferencias entre variantes, no.
