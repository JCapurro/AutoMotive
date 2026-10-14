# deRuedas

Clasificados de autos de Cuyo: unos 11.700 usados publicados (9.112 en Autos y 2.581 en Utilitarios y Camionetas el 9 de octubre de 2026), alrededor del 78 % en Mendoza y el resto sobre todo en Córdoba, San Juan y Buenos Aires. El sitio es `www.deruedas.com.ar`. **`deruedas.com` es un dominio estacionado y no se usa**: ni el collector ni el CLI lo reconocen como esta fuente.

Código publicado en `main` y activo en producción desde el 14 de octubre de 2026. Ver [Activación](#activación).

## Operación

| ID | Origen | Recorrido | Cadencia inicial |
|---|---|---|---|
| `deruedas` | [deRuedas](https://www.deruedas.com.ar/bus.asp?segmento=0&condicion=Usados) | Búsqueda pública por marca y modelo en los segmentos Autos y Utilitarios y Camionetas. Un target por modelo, como Mercado Libre o Autocosmos. | 1 hora por target; fichas cada 6 segundos |

A diferencia de las agencias, no es un target de inventario (`INVENTORY_TARGET = False`): el volumen obliga a buscar por modelo. Activa `STRICT_DETAIL_ID`: enriquecimiento y reprocesado comprueban fuente e ID antes de tocar el aviso guardado. Registro en `collectors.REGISTRY`, `config.SOURCES`, `tools/scraper_cli.py` (`www.deruedas.com.ar` y `deruedas.com.ar`) y `tools/collector_repairs.py`.

Migración: `supabase/migrations/20261023180000_deruedas_source.sql`. Inserción idempotente (`on conflict (id) do nothing`) que preserva ajustes del operador; `supabase/seed.sql` incluye la misma fila (prioridad 140, intervalo de fichas 6). La web obtiene su lista desde `sources.enabled`.

## Contrato de búsqueda

El sitio **ignora en silencio** cualquier filtro que no reconoce y responde con toda la marca, mientras el título, el breadcrumb y el canonical siguen nombrando el modelo pedido. Por eso cada recorrido prueba qué se aplicó antes de leer una sola tarjeta.

- **Segmentos.** `0` Autos (incluye SUV: Hilux SW4, RAV4, Corolla Cross) y `1` Utilitarios y Camionetas (Hilux, Ranger, Amarok, Kangoo…). No existe un valor “todos” y una lista (`0,1`) responde HTTP 500. Nunca se consultan motos, cuatriciclos, planes de ahorro ni camiones.
- **Catálogo por segmento.** `busCraw.asp?…&weNeed=divFiltros` devuelve las marcas y los modelos con stock usado. Se guarda 30 minutos en memoria. La ortografía es la del segmento (`Kia` en Autos, `KIA` en Utilitarios; `Mercedes Benz`, `CRV`). El modelo se resuelve por coincidencia exacta sin signos ni acentos (`CR-V` → `CRV`); si ningún segmento lo lista así, por prefijo (`Onix Plus` → `Onix`, porque “Plus” es una versión) o por contención (`SW4` → `Hilux SW4`, hasta tres candidatos). Se consulta cada segmento que lo liste: Etios figura en ambos, Hilux sólo en Utilitarios. Si el catálogo no lista la marca o el modelo, el resultado es vacío y completo. Una marca tildada sin ningún modelo `Marca:…` falla (`model catalog missing`) y no se guarda: el sitio sólo lista marcas con stock, así que es un cambio de marcado. Una búsqueda sin marca falla antes de pedir nada: el sitio redirige a la portada cualquier modelo sin marca.
- **Generaciones y versiones.** El sitio lista aparte modelos que el catálogo de vehículos archiva bajo otro: `Fiesta KD`, `CrossFox`, `Nuevo Palio`, `Corsa II`, `Gol Country`, `Grand Siena` y `Uno Evo` se recorren junto con `Fiesta`, `Fox`, `Palio`, `Corsa`, `Gol`, `Siena` y `Uno`, cada uno con su propio pedido. Nunca `Gol Trend`, `Corolla Cross` ni `Hilux SW4`, que son modelos distintos. Al revés, el sitio archiva el Onix Plus como `Onix` con versión `Plus …` y el Stepway como `Sandero` con versión `Stepway …`: el aviso guarda `Onix Plus` o `Stepway` sólo si esa es la primera palabra de la versión (`Joy+` y `LTZ … AT Plus` siguen siendo Onix), y un target Stepway busca en Sandero.
- **Pedido.** `bus.asp?segmento=S&marca=Marca&modelo=Marca:Modelo&condicion=Usados&order=6`, un modelo por pedido, con `%20`, `%3A` y acentos en UTF-8. `order=6` es “Últimos publicados”. Nunca se envían `kilometraje` (el sitio descarta los avisos sin km) ni `precio_*` (son posiciones del deslizador, no pesos): km y precio se filtran en el worker.
- **Prueba de filtro aplicado.** En la primera página: JSON-LD `SearchResultsPage` con `numberOfItems`; marca tildada igual a la enviada; chip del modelo (`toggleModeloLink cerrarItem_4`) con `marcaval`/`modeloval` exactos; lista de modelos reducida a ese único valor. En todas las páginas: cada tarjeta debe ser de esa marca y ese modelo. Cualquier diferencia falla con `model filter not applied`.
- **Años.** Se envían sólo dentro del deslizador del sitio (los últimos 30 años): `anio_1` y `anio_2` fuera de ese rango se ignoran sin aviso. Si se envían, la página debe mostrar su chip, y van en todas las páginas del recorrido. El año se verifica además tarjeta por tarjeta. Un resultado cero con filtro de año se comprueba sólo con la primera página sin el filtro: si el modelo tiene stock, el cero es real y el resultado es vacío y completo.
- **Cero resultados** para un modelo que el catálogo lista falla (`catalog lists model but search found 0`) y descarta ese catálogo para que la corrida siguiente lo resuelva otra vez.
- **Paginación.** 30 tarjetas por página; de la segunda en adelante `busCraw.asp?…&weNeed=divBusqueda&pag=N`. La continuación se lee sólo de `<script class="newScript"> masContenido = …`: `bus.asp` declara además `var masContenido = false;` en su cabecera en todas las páginas. El recorrido termina con el marcador en falso, una página corta, la lista vacía posterior al final o una página más allá del contador. Tope de 60 páginas (1.800 avisos) por consulta: si se supera, el resultado se conserva como incompleto.
- **Tarjetas fuera de usados.** Una unidad nueva o un plan suelto se descarta en silencio. Una página con tarjetas y ninguna de usados falla (`cards outside used stock`): `condicion=Usados` nunca devolvió otra cosa, así que es un cambio del filtro o del marcado.
- **Completitud.** Los avisos se deduplican por `cod` entre páginas, segmentos y modelos. Si faltan más de `max(2, 2 %)` respecto del contador, la consulta se recorre una vez más; si sigue faltando, la corrida queda incompleta (`deruedas: 60/65 avisos`) sin perder lo leído. Que un aviso falte en la búsqueda nunca lo da de baja.
- **Ritmo.** `robots.txt` pide `Crawl-delay: 5` y prohíbe `/special/`. Todo el proceso comparte un turno cada 6 segundos entre búsquedas, fichas y reintentos. El turno se toma recién al despertar, y el siguiente cuenta también desde el final del pedido anterior: un loop demorado o un handshake lento nunca acercan dos pedidos. Sólo se piden `bus.asp`, `busCraw.asp` y `/vendo/…?cod=N`, y una ruta con `.` o `..` (también como `%2E%2E`) se rechaza antes de pedirla; nunca el teléfono, el formulario de contacto ni `ajax.asp`.
- **Transporte.** Las redirecciones no se siguen (en búsquedas pierden el orden o el modelo y fallan la corrida). 401/403/429 y un desafío de Cloudflare son bloqueo; un 5xx se reintenta una vez a los 30 segundos. El cuerpo se decodifica como UTF-8 estricto: el sitio no declara charset.

## Precio, vendedor y bajas

**Precio.** Se toma el visible: `$` es ARS y `U$` es USD. Los metadatos del sitio siempre están en pesos (convierte los avisos en dólares a su propio tipo de cambio: `U$ 19.000` figura como `29260000 ARS`) y no se usan como precio; quedan en `extra.precio_ars_sitio`. `Consultar` o un valor de 1 quedan sin precio. La etiqueta “Entregá $ X y cuotas” es el simulador de financiación del sitio: no es el precio, no entra al título y no marca el aviso como parcial. En la ficha, el precio de la tabla debe coincidir con el del encabezado.

**Precio parcial.** Además del título, la ficha marca el precio como parcial cuando el comentario del vendedor habla de cuotas pagas, plan de ahorro, adjudicado o círculo cerrado (por ejemplo `32 CUOTAS PAGAS`). No se usa la detección general de palabras sobre la descripción porque las agencias pegan “financiación en cuotas” en avisos con precio total.

**Vendedor.** En la tarjeta sólo es `agencia` cuando muestra el logo de un cliente del sitio dentro del enlace del vendedor; el resto queda sin definir. Ese enlace era `?codUsr=N` el 9 de octubre de 2026 y el 14 ya era `/@nombre` (`refreshparam="nombreUsuario"`): se aceptan los dos y el valor queda en `extra.codUsr` o `extra.nombreUsuario`. En la ficha es `agencia` si hay cualquier señal de comercio (enlace de cliente, “Vehículos Vendidos”, mapa u horarios) y `particular` en caso contrario. El nombre sólo se conserva para clientes del sitio: en los demás es el nombre de una persona.

**Combustible, caja y km.** El combustible es el del aviso, no el del catálogo (hay autos con GNC cuyo catálogo dice Nafta). La caja sale del catálogo sólo cuando la ficha indica “Información de catálogo”. Sin km informado queda desconocido: el marcador `KMT 1` y la condición `NewCondition` del sitio no significan nada.

**Bajas.** Dos pruebas, nada más: la ficha con el recuadro “este vehículo no está disponible” (aunque sus metadatos digan `InStock`) o un 302 exactamente a `https://www.deruedas.com.ar/` para una URL con `cod` numérico. Una URL sin `cod` numérico redirige igual, por eso se rechaza antes de pedirla. Identidad distinta, portada, estado ambiguo, una ficha sin el recuadro del vendedor, 404/410, 5xx o un desafío fallan sin dar de baja. El recuadro “no disponible” sólo cuenta dentro del recuadro del vendedor: el mismo texto en un comentario no prueba nada. El sitio sirve por `cod` e ignora la ruta, así que la identidad se prueba con `sku` y canonical.

**Página guardada.** `raw_pages` conserva un JSON con los campos públicos del aviso, reprocesable. Sólo se lee como tal una copia que empieza con ese JSON: dentro de una ficha en vivo sería texto del vendedor y se ignora. No guarda el nombre del vendedor particular, dirección, mapa, horarios, enlace de WhatsApp, email, el texto generado por “Simón”, avisos similares ni el simulador. El teléfono nunca está en el HTML.

**Ubicación.** El sitio escribe `Provincia, Departamento`; el aviso guarda `Departamento, Provincia`. `normalization/geo.py` suma los departamentos de Mendoza, San Juan y San Luis con su provincia y las capitales (`Capital, Mendoza`), porque Luján, Junín, San Martín, Rivadavia o Santa Rosa también son localidades a 1.000 km: antes `Junín, Mendoza` quedaba en Junín, Buenos Aires. Por la misma razón suma `San Justo` y `General San Martín` de Córdoba y `San Justo` y `San Martín` de Santa Fe, en sus cabeceras (San Francisco, Villa María, San Justo y Sastre): antes quedaban en el conurbano.

## Riesgos conocidos

- **El precio parcial detectado en la ficha no persiste.** La siguiente lectura de tarjetas lo recalcula desde el título. Hasta ajustar la normalización, el control estadístico del motor de oportunidades es la única defensa duradera.
- **Un 302 transitorio a la portada** de un aviso vivo se leería como baja. No se observó en unas 90 fichas.
- **El catálogo parece listar sólo modelos con stock** (no demostrado). Si no fuera así, un modelo sin avisos fallaría en cada corrida en lugar de devolver vacío.
- **Generaciones y versiones a mano.** Las dos tablas de `collectors/deruedas.py` (generaciones que se recorren con su modelo y versiones archivadas como otro modelo) cubren lo visto el 9 de octubre de 2026. Si el sitio lista una generación nueva como modelo propio, o archiva otra versión dentro de un modelo, hay que sumarla: hasta entonces esos avisos no se piden o quedan con el modelo del sitio. `207 CC`, `308 CC`, los Picasso y `Yaris Cross` quedan fuera a propósito aunque la normalización los archive bajo `207`, `308`, `C3`, `C4` o `Yaris`.
- **Modelos con nombre más largo en otro segmento.** Con coincidencia exacta en un segmento no se buscan variantes en el otro (`Hilux` no trae `Hilux SW4`, pero tampoco traería un hipotético `Partner Furgón`).
- **Tipo de vendedor heurístico.** No hay un indicador explícito: una agencia sin ninguna señal queda como particular y un particular con dirección publicada, como agencia.
- **El enlace del vendedor en la tarjeta ya cambió una vez** (de `codUsr` a `nombreUsuario`, entre el 9 y el 14 de octubre de 2026). Si vuelve a cambiar, las tarjetas dejan de marcar agencias sin fallar; la ficha sigue clasificando al vendedor. Una corrida con 0 agencias en un modelo con stock de concesionarias es la señal.
- **Vendido, pausado y vencido no se distinguen.**
- **Umbrales de Cloudflare desconocidos.** Las pruebas nunca superaron un pedido cada 6 segundos.
- **Un aviso puede cambiar de modelo** con el mismo `cod`; se acepta y la ingesta lo actualiza.
- **`Capital, Buenos Aires` es ambiguo** y queda para el geocodificador. Los demás departamentos de Córdoba y Santa Fe también, salvo San Justo y (General) San Martín, que llevan la provincia porque comparten nombre con localidades del conurbano.
- **Otros departamentos homónimos.** Algunos siguen cayendo en una localidad de Buenos Aires con el mismo nombre: `Caseros, Santa Fe` queda en Caseros (Tres de Febrero) y `Victoria, Entre Ríos` en Victoria (San Fernando).
- **El combustible lo carga el vendedor** y puede estar mal.
- **Escala.** Un target de marca sola puede necesitar 60 pedidos (6 minutos) por segmento, y cada generación que el sitio lista aparte suma al menos un pedido al target de su modelo. Un modelo que se queda sin stock produce corridas vacías, que la salud de la plataforma interpreta igual que en las demás fuentes por modelo.
- **Múltiplo exacto de 30 resultados** sin probar en vivo; las reglas de corte lo cubren con un pedido extra.
- Cada ficha leída suma una visita al contador público del aviso: sólo se enriquecen los avisos con coincidencias.

## Validación

El relevamiento del sitio es del 9 de octubre de 2026. Las páginas públicas guardadas ese día pasaron por el collector sin pedir nada:

| Muestra | Resultado |
|---|---|
| Búsquedas de usados | **70 páginas** (63 con tarjetas), **1.690 tarjetas** leídas sin excepciones, 869 avisos distintos. 173 en USD, 228 sin km, 732 con logo de agencia, 27 sin versión; todas con año, ubicación y foto. |
| Prueba de filtro | 36 primeras páginas: 26 aceptadas y 10 rechazadas, que son las de filtro ignorado, marca desconocida, segmento ajeno o año fuera del deslizador. |
| Fichas | 36 respuestas: **23 activas**, **11 bajas** (6 redirecciones a la portada y 5 recuadros “no disponible”) y 2 rechazadas por `cod` no numérico. Las dos portadas guardadas también se rechazan. |
| Reprocesado | JSON guardado idéntico al original en 34 de 34 fichas; 21 pares tarjeta/ficha coinciden en título, precio, año, km, ubicación, combustible y primera foto. |

Ejemplos: Corolla `830433`, 2024, 27.000 km, ARS 38.500.000, agencia cliente, 8 fotos. Maserati `828256`, USD 180.000 (ARS 277.200.000 según el sitio), sin km. Cronos `822494`, ARS 12.000.000 marcado como parcial por “32 CUOTAS PAGAS”.

Suite offline sobre `d7652a0`: **766 passed, 21 skipped, 178 deselected**, sin fallos (en `7a45eb1`, sin el cambio: 682, 21 y 171; con el cambio: 764). Las 82 pruebas nuevas son 79 de deRuedas (`worker/tests/test_deruedas.py`) y 3 de ubicación (`worker/tests/test_location_radius.py`). Los fixtures son recortes de páginas reales sin nombres de particulares, direcciones, teléfonos, emails ni enlaces de WhatsApp; el nombre redactado conserva el marcado en vivo (`span` con `font-size:20px`) para que una lectura indebida de ese selector falle en las pruebas.

**Prueba en vivo (14 de octubre de 2026)**, sólo a través del collector, con el código de `scraper_cli` (el pool de la base, que la CLI abre para el filtro por radio, se omitió):

| Pedido | Resultado |
|---|---|
| `deruedas marca=Toyota modelo=Etios` | **167 avisos** (166 en Autos y 1 en Utilitarios), recorrido completo. 5 en USD, 162 en ARS, 21 sin km; todos con año, versión, ubicación y foto, sin duplicados. 9 pedidos en 52,8 s, nunca menos de 6,28 s entre uno y otro. |
| Vendedor en tarjetas | La primera corrida dio **0 agencias**: el enlace del vendedor había cambiado a `/@nombre`. Corregido y probado con `deruedas_cards_slug.html` (tarjetas reales de ese día); las 9 páginas de una segunda corrida idéntica, releídas con la corrección, dan **67 agencias**, una por cada tarjeta con logo de cliente. |
| `detail …/Etios/Usados/Mendoza?cod=830448` | 200, activo: Toyota Etios 1.5 4ptas XLS 6MT, 2018, 109.000 km, ARS 19.900.000 (no parcial), Guaymallén, Mendoza, GNC, caja manual, agencia cliente, 8 fotos, 641 caracteres de descripción. Coincide con su tarjeta. |
| `detail …/Etios/Usado/Mendoza?cod=810000` | 302 a la portada: baja, “aviso eliminado (redirige al inicio)”. |
| Código corregido: `marca=Toyota modelo=Corolla Cross` | **65 avisos**, recorrido completo, sólo `Corolla Cross`, sin duplicados. 3 en USD, 1 sin km, **33 agencias**. 26,4 s. La ficha de `829641` (2022, 111.000 km, ARS 41.500.000, Godoy Cruz, Mendoza) es activa, de agencia, con 8 fotos y coincide con su tarjeta. |

Desde `worker/`, sin ingesta ni notificaciones (cada pedido espera su turno de 6 segundos):

```powershell
python -m tools.scraper_cli deruedas marca=Toyota modelo=Hilux
python -m tools.scraper_cli deruedas marca=Chevrolet modelo=Onix anio_min=2018
python -m tools.scraper_cli detail 'https://www.deruedas.com.ar/vendo/Toyota/Corolla/Usados/Mendoza?cod=830433'
python -m tools.scraper_cli detail 'https://www.deruedas.com.ar/vendo/Toyota/Corolla/Usados/Mendoza?cod=830433' --html ficha.html
```

## Activación

**Activa desde el 14 de octubre de 2026.** El worker del VPS corre `95e3a7b`, que incluye el collector (desplegado y reiniciado a las 11:21). La migración `20261023180000_deruedas_source.sql` está aplicada en producción: es el `max(version)` de `supabase_migrations.schema_migrations` y `sources` tiene `deruedas` habilitada. Comprobado con el script de aplicación, que encontró la versión ya registrada y terminó sin cambios. Las corridas en producción todavía no se revisaron en `collector_runs`.

Para activar una fuente nueva con este mismo esquema, en este orden: actualizar el worker del VPS a `main` y reiniciarlo; después aplicar la migración en producción, con una versión mayor que el `max(version)` de `supabase_migrations.schema_migrations` (otras sesiones aplican migraciones desde ramas). En el orden inverso la web ofrecería deRuedas antes de que el worker pueda recorrerla. `supabase/seed.sql` también la habilita: un `db push --include-seed` desde este checkout la activa igual que la migración. Los perfiles que abarcan todas las fuentes la incorporan al habilitarse; los que eligen fuentes conservan su selección. La primera corrida de cada target es un bootstrap silencioso.
