# Plan: filtro de color en las búsquedas

Pedido de Juan del 12/11/2026: poder filtrar las búsquedas por color. La descripción casi nunca lo dice, así que la idea es sacarlo con IA y explorar otras formas de obtener y medir el dato. Juan tomó todas las decisiones el 12/11 (sección 7). La Fase 0 está hecha (resultados en [COLOR.md](COLOR.md)) y Juan aprobó la recomendación el 12/11: Fases 1–3 en curso.

## 1. Lo que hay hoy (medido en producción el 12/11/2026)

- No hay filtro de color. El matching tiene una preferencia blanda, `preferences.colors`, que suma puntaje sin descartar y compara el texto crudo del aviso («gris oscuro» no es «gris»). Ninguna de las 440 búsquedas la usa y la web no la ofrece.
- Hay 58.862 avisos activos. El título o la descripción nombran un color en el 3 % (1.843), contando falsos positivos («interior negro», «llantas negras»). Por texto no alcanza.
- Algunas fuentes publican el color en la ficha. Se escanearon las últimas 400 fichas guardadas de cada fuente (`raw_pages`):

| Fuente | Fichas con color | Dónde | Hoy |
|---|---|---|---|
| Mercado Libre | 99 % (397/400) | Tabla «Color» y JSON-LD | Se guarda (`attributes.Color`) |
| Kavak | 78 % (311/400) | JSON-LD `color` | Se guarda (`attributes.color`) |
| Grupo Randazzo | 100 % de los avisos | «Color» | Se guarda |
| Autocosmos | 97,5 % (390/400) | `itemprop="color"` en la ficha, y «… color Negro Vulcano precio …» en la tarjeta del listado | **No se lee** |
| Facebook | 1,5 % (6/400) | Solo texto libre. El «Color exterior» del fixture no aparece en las 300 fichas guardadas | — |
| Rosario Garage | 2,7 % | Solo texto libre | — |
| deRuedas, V6, Car One, Autocity, Mardel, Santa Fe | 0 % | — | — |

- Lo que importa son los avisos que le llegan a alguien. En los últimos 7 días hubo **872 avisos con match** (sin contar backfill), unos 125 por día:
  - 455 (52 %) ya tienen color, casi todos de Mercado Libre (444 de 454, porque su ficha se lee para todo aviso con match).
  - **310 (36 %) son de Facebook:** no tienen color y sus fotos hoy no se descargan (hosts de Meta bloqueados en el código y `risk.photo_hash.skip_sources`).
  - El resto, sin color: Rosario Garage 36, deRuedas 23, Autocosmos 20, Kavak 16, Mercado Libre 10, otros 2.
- El pase de fotos de duplicados (`pipeline/photo_hash.py`) ya está prendido: baja hasta 600 fotos por día con un descargador seguro.

## 2. Opciones para obtener el dato

| Opción | Costo | Precisión esperable | Cobertura | Rol |
|---|---|---|---|---|
| 1. Dato declarado por la fuente | 0 | Muy alta: lo cargó el vendedor | Mercado Libre, Kavak, Randazzo. Autocosmos, con un cambio de parser | Primera capa, siempre |
| 2. Reglas sobre el texto | 0 | Media | ~3 % | Solo con ancla («color blanco», «color: gris»), ignorando interior, tapizado, llantas y techo |
| 3. Píxeles de la foto, sin IA (Pillow ya está en el VPS) | 0 | Baja a media: el fondo, el cielo, los reflejos y los carteles de agencia confunden, y blanco, gris y plata se mezclan | Todo aviso con foto | Solo como control en la medición |
| 4. Modelo de visión local en el VPS (CLIP/SigLIP, o recortar el auto y tomar el color dominante) | 0 por foto, pero suma 300–800 MB de dependencias, CPU y mantenimiento | Media a alta | Todo aviso con foto | Solo si no se quieren mandar fotos a un tercero |
| 5. IA de visión por API: OpenAI Luna, el proveedor ya configurado (Claude como alternativa, por la misma capa) | ~US$ 0,0001 por aviso | La más alta. Puede decir «no se ve el auto» (interior, cartel) | Todo aviso con foto descargable | **Propuesta** para lo que la fuente no trae |

Descartadas: el informe de dominio (DNRPA) es pago y necesita la patente, el VIN no codifica el color y el catálogo no sirve porque el color no depende del modelo.

## 3. Cómo medir antes de elegir (Fase 0)

- **Verdad de referencia gratis:** los 7.323 avisos activos con color declarado (Mercado Libre, Kavak y Randazzo, más Autocosmos cuando se lea). Se arma una muestra de 300, pareja por color y fuente, más 60 de deRuedas y Rosario Garage revisados a mano. Las fotos de particulares (2 por aviso en promedio) no se parecen a las de agencia.
- Sobre la misma muestra se corren:
  - la opción 3 (píxeles);
  - la opción 5 con una foto;
  - la opción 5 con un mosaico de las 3 primeras fotos en una sola imagen. Cuesta lo mismo y salva el aviso cuya primera foto es un cartel o el interior.
  - La opción 4, solo si la 5 no llega al umbral.
- Métricas: acierto por grupo, matriz de confusión (blanco, gris y plata), porcentaje de «no se ve», tokens y costo reales por aviso (el proveedor ya los registra) y latencia.
- Umbral propuesto: ≥ 90 % de acierto entre los que la IA marca con confianza alta. Lo demás queda sin dato.
- Costo: menos de US$ 0,10. Solo se lee la base y se llama a la API; nada cambia en producción.
- **Medición continua** después del lanzamiento:
  - Un 2 % de los avisos con color declarado pasa también por la IA, para seguir el acierto real.
  - En /admin se ve la cobertura por fuente y por método.

## 4. Diseño

### Paleta (propuesta)

| Código | En el filtro | Incluye |
|---|---|---|
| `blanco` | Blanco | perla, banquise, summit, cristal, marfil |
| `negro` | Negro | vulcano, black meet, noir |
| `gris` | Gris o plata | plateado, plata, gris oscuro y claro, grafito, aluminium, silverstone |
| `azul` | Azul o celeste | celeste, azul noche, petróleo |
| `rojo` | Rojo o bordó | bordó, rojo fuego |
| `verde` | Verde | |
| `beige` | Beige o marrón | marrón, café, champagne, dorado, bronce |
| `otro` | Otro color | amarillo, naranja, violeta, rosa |

Gris y plata van juntos porque ni los vendedores los separan: en Mercado Libre hay 2.045 «gris», 573 «plateado» y además «gris plata».

### El color de un aviso

- Se guarda en `listings.color` (código o `null`), con el origen en `listings.attributes._color = {"method": "source" | "text" | "vision", "raw", "confidence", "model", "v"}`, igual que `body_type` y `_body_type`. Queda fuera de `KEY_ATTRS`: completarlo no genera snapshot ni `listing_updated`.
- Orden: fuente, después texto con ancla, después foto. Si una ficha llega después con color declarado, le gana a la foto.
- `normalization/color.py` pasa los valores crudos a códigos (la tabla de arriba).
- **IA solo donde hace falta:** avisos sin color de fuente ni de texto que cumplan una de dos condiciones:
  - pasan los demás filtros de una búsqueda con color;
  - tienen un match, para mostrar el color en la tarjeta.

  Hoy serían unos 60 por día con Facebook y 12 sin Facebook.
- La foto se baja con el descargador de duplicados (`pipeline/photo_hash.py`): solo https públicas, tope de bytes y un pedido por host por segundo. Para el color también se aceptan los hosts de Meta; el pase de duplicados los sigue bloqueando. La foto se achica a 512 px, viaja en base64 y no se guarda.
- El proveedor suma el método `listing_color` en OpenAI y Anthropic, con prompt y schema estrictos (`llm/prompts/listing_color.md`, `llm/schemas.py`). Devuelve código, confianza y si se ve el auto. Con confianza baja o «no se ve», queda `null`.
- La configuración va en `app_config.color_vision = {enabled, daily_cap, min_confidence, skip_sources}`, editable en /admin/config. El tope diario se lleva en un registro persistente, como en `description_facts`.

### La búsqueda

- `search_profiles.filters.colors`: lista de códigos. Se omite si está vacía.
- En `matching.py`, la regla `color` va después de `body_type`:
  - si el color está en la lista, `ok`;
  - si es otro color, `fail` («color rojo; buscás blanco o gris»);
  - sin dato, `unknown`: no descarta y baja el puntaje, como hoy la caja y la carrocería dentro del modelo. La tarjeta dice «color sin confirmar».

  La preferencia blanda vieja se borra.
- La misma regla va en `preview_search` (el conteo en vivo), en el control de filtros (`search_filters_problem` y el trigger, que validan los códigos) y en el auto perdido del mail 2.5 (si el aviso tiene color, tiene que coincidir). Si no, el conteo en vivo miente, como se aprendió con carrocería.
- **Antes de avisar:** dentro del lote del crawl, se pide el color en el momento para los candidatos de búsquedas con color que no lo tienen, con un tope de unos 20 s por lote. Así el aviso sale con el color ya decidido. Lo que no se resuelve a tiempo sigue la regla de «sin dato» y se completa después como backfill, sin volver a avisar.
- En la web:
  - casillas de color en el formulario, con «Cualquier color» por defecto, en los dos modos (por modelo y por carrocería: «cualquier SUV blanca»);
  - el color en el resumen de criterios;
  - la búsqueda asistida lo entiende («un Gol blanco» da `blanco`);
  - tarjeta y ficha muestran «Color: gris · según la foto» o «Color: gris · dato del aviso»;
  - la razón del match aparece en mails y WhatsApp.

## 5. Fases

0. **Medición** (sección 3). Entregable: resultados en `docs/COLOR.md` y la elección del método con Juan.
1. **Dato gratis:** `normalization/color.py`, el color de Autocosmos (tarjeta y ficha), la migración de `listings.color` y el backfill desde lo guardado (`tools/backfill_color` y `tools.reprocess --raw --source autocosmos`).
2. **IA de visión:** el método del proveedor, el pase de color con tope diario y el backfill de los ~3.000 avisos activos con match y sin color (sin contar Facebook).
3. **Filtro:** matching, SQL (`preview_search`, control de filtros, auto perdido), web, búsqueda asistida, tarjeta y mails.
4. **Producción**, con el OK de Juan en cada paso y en el orden de siempre:
   1. Parar el worker (`wait_idle`).
   2. Mirar `max(version)` en producción (hoy `20261213120000`) y aplicar cada migración en una transacción con el insert de su versión.
   3. Desplegar el worker y correr los backfills.
   4. Recién después, mergear a `main`: Vercel despliega la web.
5. **A la semana:** cobertura por fuente, acierto de la muestra continua y costo real.

Pruebas:
- pytest: normalización, matching, Autocosmos y el proveedor con respuestas grabadas;
- pgTAP: trigger y `preview_search`;
- vitest: formulario y resumen;
- e2e: crear una búsqueda con color.

## 6. Costo

- Por aviso: ~800 tokens de entrada (foto de 512 px más instrucciones) y ~40 de salida. Luna cobra US$ 0,10 por millón de tokens de entrada y US$ 0,50 por millón de salida, o sea ~US$ 0,0001 por aviso. OpenAI no publica cuántos tokens cuenta Luna por imagen: lo mide la Fase 0.
- Volumen actual: unos 60 avisos por día con Facebook (12 sin Facebook), o sea **menos de US$ 1 por mes**.
- Backfill, una sola vez: ~4.700 avisos con Facebook o ~3.000 sin. Menos de US$ 1.
- Tope propuesto: 500 fotos por día, como mucho ~US$ 0,05 por día.
- Base: una columna de texto, despreciable frente a los 711 MB actuales.

## 7. Decisiones de Juan

Respuestas del 12/11/2026:

1. **Fotos de Facebook** (36 % de lo que llega a la gente): **se usan todas sus fotos, solo para el color** («Sí, todas», Juan, 12/11, después de ver la Fase 0; antes había aprobado solo la primera).
   - **Por qué quedaron afuera:** fue una precaución de PAR-02 (pregunta 6 de `docs/superpowers/specs/2026-11-02-par02-resto-design.md`), propuesta para el hash de duplicados. No es un límite técnico. Los motivos eran tres: las URLs vienen firmadas y vencen, los términos de uso de Meta prohíben la recolección automatizada, y son pedidos extra al CDN de Meta desde el IP del VPS.
   - **Para el color esos motivos pesan poco:**
     - La foto se baja al leer el aviso, cuando la URL todavía sirve.
     - El navegador del collector ya carga las fotos de Marketplace cuando lee los avisos (no bloquea imágenes).
     - Serían unos 45 pedidos por día, sin cookies ni sesión.
     - Se guarda solo el código de color, nunca la imagen.
   - **Lo que sí cambia:** la foto viaja a OpenAI, aunque no se guarda (`store=false`).
   - **Cómo se usa:** todas las fotos del aviso (hasta 10), como con las demás fuentes. Solo para el color y solo para los avisos que pueden llegarle a alguien. El pase de duplicados sigue sin fotos de Meta. Lo mismo podría valer para los dos colectores de Instagram, que traen pocos avisos.
   - Cobertura estimada de lo que llega a la gente: 52 % hoy, ~63 % sin Facebook y ~95 % con Facebook.
2. **Sin color:** si no se puede confirmar por ninguna vía, el dato queda «sin confirmar». El aviso llega igual, marcado así.
3. **Paleta:** gris y plata en un solo grupo.
4. **Planes:** el filtro va en todos los planes.
5. **Gasto:** OK para usar la API de OpenAI, con el tope diario.
6. **Colores dudosos (idea de Juan, 12/11):** la IA devuelve un color principal y, si duda, alternativas vecinas con probabilidad (un Beetle crema: beige 80 %, blanco 20 %). Se guarda el principal en `listings.color` y la lista en `attributes._color.candidates`. Matching: si el color buscado es el principal, `ok`; si es una alternativa con probabilidad ≥ ~20 %, también matchea, con la marca «puede ser blanco» y algo menos de puntaje. La Fase 0 midió el umbral: **30 %**, con prompt que obliga a nombrar el vecino (variante `multi3b`).
7. **Todas las fotos exteriores (Juan, 12/11):** la IA recibe todas las fotos del aviso (hasta 10, cada una aparte, detalle bajo) y descarta sola las de interior, motor o papeles. Medido: 88,6 % contra 84,3 % con 3 fotos; US$ 0,25 cada mil avisos.

## 8. Contrato de implementación (12/11, Fases 1–3)

Lo que todas las partes (worker, SQL, web) dan por hecho. Si algo de esto cambia, cambia acá primero.

**Códigos y textos.** `blanco` «Blanco», `negro` «Negro», `gris` «Gris o plata», `azul` «Azul o celeste», `rojo` «Rojo o bordó», `verde` «Verde», `beige` «Beige o marrón», `otro` «Otro color». En ese orden en el formulario.

**El dato del aviso.**
- `listings.color text null`, con check contra los 8 códigos.
- `listings.attributes._color = {"method": "source"|"text"|"vision", "raw": str|null, "confidence": "alta"|"media"|"baja"|null, "model": str|null, "v": 1, "candidates": [{"color", "prob"}]|null, "photos": int|null, "at": iso}`.
- **Precedencia:** fuente > texto > foto. La visión nunca pisa un color de fuente o de texto; un color de fuente que llega después sí pisa a la visión. Completar el color no genera snapshot ni `listing_updated` (fuera de `KEY_ATTRS`).
- **Visión sin resultado:** si no se ve el auto, queda `color null` con `_color = {"method": "vision", "result": "no_visible", ...}` y no se reintenta mientras no cambien las fotos.
- **Candidatos:** son la lista completa que devuelve la IA. Cuentan los que tienen `prob >= 30` (`normalization/color.py: CANDIDATE_MIN_PROB = 30`).

**La búsqueda.** `search_profiles.filters.colors`: lista de códigos, que se omite si está vacía. `search_filters_problem` rechaza códigos desconocidos o un valor que no sea lista. Regla `color` (dura, después de `body_type`):

| Caso | Resultado | Texto |
|---|---|---|
| sin filtro | — | — |
| `color` está en la lista | `ok` | «blanco · dato del aviso» / «blanco · según la foto» |
| no está, pero un candidato con prob ≥ 30 sí | `unknown` | «color parecido: puede ser verde» |
| `color` null | `unknown` | «color sin confirmar» |
| otro color | `fail` | «es rojo, se busca blanco o gris» |

- `unknown` no descarta y baja el puntaje como cualquier filtro duro desconocido. Vale igual en búsquedas por modelo y por carrocería.
- **SQL:**
  - `public.search_colors(jsonb) returns text[]` (null sin filtro);
  - `public.listing_color_fits(p_color text, p_attrs jsonb, p_wanted text[]) returns boolean`: true si no hay filtro, si el color es null, si está en la lista o si un candidato ≥ 30 está en la lista;
  - `preview_search` usa `listing_color_fits`;
  - el auto perdido del mail 2.5 usa la regla estricta: color null o en la lista, sin candidatos.
- La preferencia blanda `preferences.colors` se borra (0 de 440 perfiles la usan).

**Visión.**
- Modelo y llamada:
  - el método `listing_color` del proveedor (OpenAI; Anthropic con la misma firma);
  - prompt y schema de la variante `todas` de la Fase 0: hasta 10 fotos, cada una de 512x384 a lo sumo, JPEG, `detail: low`;
  - `store: false`, `reasoning.effort: none`.
- Descarga: el descargador seguro de `pipeline/photo_hash.py`, con los hosts de Meta permitidos solo para color.
- Qué avisos se miran: activos, sin color de fuente ni de texto, que tienen un match o que son candidatos de una búsqueda con `filters.colors`. Con búsquedas de color, se resuelve inline antes de avisar, con tope de ~20 s por lote.
- `app_config.color_vision = {"enabled": true, "daily_cap": 3000, "min_confidence": "media", "skip_sources": []}`. El contador diario es persistente.
- Con confianza por debajo de `min_confidence`, el color principal queda null pero se guardan los candidatos.

**Web.**
- **Formulario:** casillas «Cualquier color» (por defecto) más los 8 colores, en los dos modos (por modelo y por carrocería).
- **Resumen de criterios:** muestra los colores elegidos.
- **Tarjeta y ficha:** «Color: gris · según la foto» / «· dato del aviso». Cuando la búsqueda tiene filtro de color y el aviso no tiene dato, «color sin confirmar».
- **Búsqueda asistida:** entiende «un Gol blanco».

**Migración.** `20261214120000_listing_color.sql`. El máximo en producción es `20261213120000`.
