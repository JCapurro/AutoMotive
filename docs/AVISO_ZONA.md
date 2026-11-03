# Aviso de zona

Juan, 02/11/2026: una búsqueda no se amplía sola a todo el país. Si su zona casi no tiene publicaciones, se lo decimos con números y la persona decide ampliar el rango con un toque.

## Cuándo aparece

- Su interruptor está prendido: `app_config.zone_notice.enabled` es `true`. Sin la fila, el aviso queda apagado. En producción la fila está prendida desde la migración. Una base que aplicó la copia que entró a `main` con #83 no la tiene (ver «Cambios que acompañan»).
- La búsqueda está activa, tiene marca y modelo, y una sola zona propia (origen + radio > 0, sin `extra_locations`).
- Muestra 3 resultados o menos (`search_result_counts.all_count`).
- Ya está lista: tiene `bootstrapped_at` y no tiene `rematch_requested_at`, y ninguna fuente está leyendo el mercado para ella (`onFirstRead`, `lib/search-collection.ts`).
  - Se espera la primera lectura de una fuente (`first_run_done` apagado).
  - También se espera una lectura nueva si lo último que leyó la fuente es de más de un día antes de la búsqueda (`staleAt`). Pasa con una fuente que vuelve después de un día inactiva: conserva `first_run_done` (`targets.sync_targets`). Ahí solo cuenta una corrida terminada después de crear la búsqueda.
  - Se espera mientras esa corrida está en curso, y 3 minutos después de que termina, mientras el worker cruza su lote con las búsquedas.
  - Si la corrida no arrancó, se espera como máximo 5 minutos desde que la búsqueda necesita la fuente: lo más tarde entre su creación y la de la fuente.
  - Una lectura fallida o vacía no frena el aviso más que eso. Las fuentes sin fecha dejan `first_run_done` apagado después de una lectura vacía, y lo frenarían por horas.
- Lo que no se pudo leer responde «todavía no»: la configuración, el perfil, el conteo, los límites del plan, las fuentes, las zonas descartadas o un `preview_search`. La tarjeta vuelve a preguntar y la página no muestra el aviso.
- No aparece si se agotó el cupo de la prueba gratis, porque ahí ya está `FreeResultLimit`.
- No aparece si la persona tocó «Dejar así» para esa misma zona (evento `zone_notice_dismissed`).
- Además, tiene que haber al menos una opción que llegue a 4 resultados.

## Opciones

- `preview_search` cuenta en paralelo, con los filtros guardados:
  - la zona actual;
  - cada radio de [100, 200] que sea mayor al actual;
  - todo el país, sin `location_label` ni `extra_locations` y sin zona.
- El estimado de una opción es `all_count` más lo que la opción agrega sobre la zona actual (nunca resta).
- Se ofrecen, como máximo:
  - el radio más chico que llega a 4;
  - «Todo el país», si también llega a 4 y suma más que ese radio.
- Si ningún radio llega a 4, o la búsqueda ya está a 200 km o más, se ofrece solo «Todo el país», si llega a 4.
- Si la prueba gratis está aplicada, el estimado se topea en lo que todavía puede mostrar: lo visible ahora más el cupo que queda, dentro de `max_visible_results`. Ahí se muestra como «N+».
  - Se comparan los números que se ven. Si los dos quedan en el mismo «N+», «Todo el país» no se ofrece: no muestra nada más y gastaría lo que queda del cupo en publicaciones lejanas.

## Dónde se muestra

- **Tarjeta del modo asistido**, después del autoguardado:
  - consulta `zoneNoticeFor` cada 5 s, solo con la pestaña visible, durante 10 minutos como máximo;
  - si se elige otra zona, se actualizan los chips y el formulario de abajo (`widenedDraft`, `searchFormKey`), para que su próximo «Guardar cambios» no la deshaga;
  - mientras el formulario tenga cambios sin guardar, las opciones quedan deshabilitadas;
  - mientras se guarda un toque, el formulario queda inerte;
  - después de un toque, el foco va al título de la tarjeta y la línea de estado dice qué cambió.
- **Página de resultados**: reemplaza a la tarjeta del bot de pocos resultados mientras se muestra, porque las dos dirían «ampliá la zona».
  - Después de un toque, un aviso breve dice qué cambió y el foco va al título de la página.
  - Cuando se va el panel de preparación pero una primera lectura todavía frena el aviso (los 3 minutos del cruce o la gracia de 5), la página se sigue actualizando sola, cada 15 a 30 s, hasta que el aviso puede decidir.
- Si un toque falla, el aviso lo dice y se puede probar de nuevo. Pasa también si «Dejar así» no pudo leer la búsqueda o guardar la elección.

## Al tocar

- **Un radio:** se cambia `radius_km`.
- **Todo el país:** sin origen ni radio, y los filtros pierden el lugar, igual que guarda el formulario «Todo el país».
- En los dos casos se pone `rematch_requested_at` y se descarta el diagnóstico del bot (`search_diagnoses.dismissed_at`).
- **«Dejar así»:** registra la zona y descarta el diagnóstico del bot si ya existe. Para una zona que se dejó así, la página no muestra la tarjeta del bot y el bot no manda su aviso (mail o Telegram).
- El toque lleva la zona que mostró el aviso, porque los números eran de esa zona. Si la búsqueda cambió desde entonces (otra pestaña u otro dispositivo), ampliar no toca nada y dice «La búsqueda cambió. Volvé a abrirla para ver su zona.». «Dejar así» no registra nada.

## Eventos

- `zone_notice_shown {profile_id, place, zone, zone_kind, cold, count_source, all_count, options}`: una vez por búsqueda y zona.
- `search_zone_widened {profile_id, place, zone_kind, from_radius, to, all_count, option_count}`.
- `search_profile_updated {profile_id, filters_changed: true, via: "zone_notice"}`.
- `zone_notice_dismissed {profile_id, zone, place}`.

## Medición

Siete días contra la semana del 26/10, leídos el día 8 y contados desde que están las tres partes: la migración, la web y el worker. Sin cuentas admin.

Las tres están en producción desde el 03/11 a las 13:11:24 UTC: la web desde las 12:59, la migración desde las 13:02:59 y el worker desde las 13:11:24. La semana va del 03/11 a las 13:11 al 10/11 a las 13:11 UTC, y se lee desde el 11/11 a las 13:11, cuando las últimas búsquedas cumplen 24 h.

- **Cohorte**, fija al crear la búsqueda: autoguardadas del modo asistido cuyo borrador no traía zona.
  - Se sacan de `search_profile_created` con `mode = 'assisted_auto'`, unido a `llm_jobs` por `llm_job_id`, con `drafts[0].values.location` y `locations` vacíos.
  - Esas búsquedas se guardaron con la zona de la conexión, a 30 km. La semana del 26/10 fueron 102.
- **Principal:** 4 resultados o más a las 24 h de creada. Base 57/102 (56%); objetivo 65% o más. Con 0 resultados a las 24 h: 30/102.
- **Adelantada:** 30% o más de los avisos de la tarjeta seguidos de una ampliación dentro de los 10 minutos. El bot logró 0 de 52.
- **Resguardo:** cupo de la prueba lleno dentro de la hora de creada. Base 18/81, sobre las búsquedas creadas desde el 29/10 11:33 UTC; tiene que quedar en 30% o menos.
- **Ojo al comparar:** el mismo cambio del worker hace que toda búsqueda nueva complete su backfill de 30 días. Antes, un lote que llegaba primero lo cortaba. Eso sube la principal y el gasto del cupo aunque nadie toque el aviso. Para separar los dos efectos, comparar también las búsquedas de la cohorte que no vieron el aviso.
- **Interruptor:** mientras está apagado, ni la tarjeta ni la página muestran el aviso. Al prenderlo de nuevo, la página puede mostrárselo a las búsquedas de ese rato. Para separar quién lo vio, usar el evento `zone_notice_shown`, no la hora de creación. Cada cambio del interruptor queda en el historial de `/admin/config` (`admin_config_audit`).
- **Corte de `preview_search`:** 2026-11-03 13:02:59 UTC, cuando se aplicó la migración en producción. Desde ahí cambia el significado de `assisted_review_shown.preview_count`.

## Cambios que acompañan

- **Migración `20261206120000_preview_zone_rule.sql`:** `preview_search` cuenta la zona como matching.
  - Las zonas inválidas se saltean. Antes, un lugar extra no numérico daba error, y un radio 0 (o un lugar extra sin radio) dejaba afuera toda publicación con coordenadas.
  - Con zona, una publicación sin coordenadas no pasa.
  - También crea `app_config.zone_notice = {"enabled": true}`, el interruptor del aviso. Si la fila ya existe, no la toca.
  - Aplicada en producción el 03/11/2026 a las 13:02:59 UTC, con el OK de Juan.
  - La copia que entró a `main` con #83 (`a6f1d7d`) no tenía la fila. La que se aplicó en producción sí, y el PR del interruptor dejó el archivo igual a esa.
  - Una base que aplicó la copia de `main` tiene la versión registrada y no vuelve a correr el archivo. Le falta la fila, así que el aviso queda apagado hasta insertarla: `insert into public.app_config(key, value) values ('zone_notice', '{"enabled": true}');`.
- **Interruptor (`app_config.zone_notice`):** con `enabled` en `false` desde `/admin/config`, el aviso desaparece sin deploy.
  - La página no cuenta ni muestra nada. Donde corresponda, vuelve la tarjeta del bot de pocos resultados.
  - `zoneNoticeFor` responde «no» antes de leer nada, y la tarjeta del modo asistido deja de preguntar.
  - Si `app_config` no se puede leer, la página y la tarjeta responden «todavía no», como con cualquier lectura fallida: no muestran el aviso, la tarjeta vuelve a preguntar y, donde corresponda, la página deja la tarjeta del bot de pocos resultados.
  - Las zonas que se dejaron así se siguen respetando: la página no muestra la tarjeta del bot y el bot no avisa por ellas.
  - Los botones de un aviso que ya estaba en pantalla siguen funcionando.
- **Worker (`scheduler.py`):**
  - Con un rematch pendiente, lo que un lote encuentra y ya estaba guardado antes del pedido es backfill, no novedad. Lo que se guarda por primera vez después del pedido sí es novedad.
  - Ejemplo: una publicación de hace días que la zona ampliada ahora alcanza.
  - Un lote ya no da por lista una búsqueda nueva. Solo la marca `rematch.run_pending`, después de su backfill de 30 días.
  - Test: `worker/tests/test_zone_edit_postgres.py`.
- **Bot de pocos resultados (`pipeline/low_results.py`):** no manda su aviso por una búsqueda cuya zona actual su dueño dejó así. Igual guarda su diagnóstico. Un evento con una zona mal armada se ignora. Test: `worker/tests/test_low_results_postgres.py`.
- **Formulario (`search-form.tsx`):** la nota de Ubicación pasa a «Si elegís una zona, quedan afuera las publicaciones que no informan dónde están.» en todos los formularios (nueva búsqueda, editar y la tarjeta). La anterior decía que las publicaciones sin ubicación no se descartan, y desde el 26/10 eso ya no es cierto para una búsqueda con zona.

## Efectos conocidos

- Pasar a todo el país puede mover la ciudad de Facebook del modelo. La elige la búsqueda más vieja con lugar entre las que siguen ese modelo, de cualquier cuenta (`pipeline/crawl.py`).
- Ampliar gasta cupo de la prueba con el rematch, porque `admit_free_result` corre con cada match, también los de backfill. El rematch va de lo más nuevo a lo más viejo, no por cercanía, y «Todo el país» puede llenar el cupo de una vez. El cupo es por cuenta y no se repone: lleno, la cuenta no recibe más alertas de publicaciones nuevas en ninguna de sus búsquedas. Por eso es el resguardo de la medición. Si el resguardo se pasa, el aviso se apaga con su interruptor, sin deploy. Las ampliaciones ya hechas y el cupo gastado quedan como están.
- Una búsqueda nueva queda lista solo con su rematch. Si el rematch falla siempre, la búsqueda sigue en preparación (sin alertas, sin bot y sin aviso), y `run_pending` la reintenta cada 15 s con una fila nueva en `pipeline_errors`. Antes, el primer lote la daba por lista sin su backfill.
- El umbral de 3 está fijo en el código (`ZONE_NOTICE_MAX_RESULTS`) y no sigue a `app_config.low_results.max_results`: si se cambia ahí, el aviso y el bot dejan de coincidir.

## Fuera de alcance

- La prueba gratis no se toca.
- Los mails y la página que explican la prueba van aparte.

## Decisiones de Juan (03/11/2026)

- La regla de «lista» queda como está: primera lectura o lectura nueva de una fuente vieja, 3 minutos para el cruce y gracia de 5 minutos.
- La tarjeta mantiene «Búsqueda guardada y activa» y cambia solo el texto de abajo.
- El aviso cuenta lo que se ve en la búsqueda: `count_source` queda fijo en `all_count`.
- El bot no manda su aviso para una zona que se dejó así.
- El aviso tiene un interruptor para apagarlo sin revertir (`app_config.zone_notice`).
- La migración se aplicó en producción el 03/11 a las 13:02:59 UTC.
- Los textos nuevos que sumó la revisión, aprobados:
  - «Listo: dejamos la zona como está.»
  - «No pudimos ampliar la zona. Probá de nuevo.»
  - «No pudimos guardar tu elección. Probá de nuevo.»
  - «La búsqueda cambió. Volvé a abrirla para ver su zona.»
  - «Tenés cambios sin guardar abajo: guardalos primero.» (tarjeta, mientras el formulario de abajo tiene cambios)
  - «Reanudá la búsqueda para ampliar la zona.»
  - la nota de Ubicación del formulario: «Si elegís una zona, quedan afuera las publicaciones que no informan dónde están.»
- También aprobó los tres que faltaban:
  - el título de la página con resultados: «En tu zona hay solo N publicaciones ahora.»;
  - la línea de zona: «Buscamos a 30 km de Laferrere.»;
  - las confirmaciones: «Listo: ahora buscamos a 200 km de Laferrere.» y «Listo: ahora buscamos en todo el país.».
