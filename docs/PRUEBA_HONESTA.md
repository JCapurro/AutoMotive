# Prueba gratis honesta (paso 1)

Juan lo aprobó el 03/11/2026 («ok aplicalo»), con la reserva detrás de un interruptor apagado. Sale de la propuesta del 02/11, armada a partir de las búsquedas de la semana del 26/10.

## Por qué

La prueba gratis muestra hasta 50 resultados por cuenta, para siempre (`20261118120000_free_results_cap_50.sql`). Lo ya publicado entra primero, así que se llena enseguida:

- Desde el 29/10, 26 cuentas la llenaron. 22 lo hicieron en los primeros 10 minutos después de crear su única búsqueda (mediana: 54 segundos).
- Con la prueba llena no llegan avisos de autos nuevos, solo bajas de precio de lo que ya se ve.
- Mientras tanto, el mail de bienvenida contaba lo que la prueba oculta y prometía avisos «apenas aparezcan». La página decía «Todavía no hay publicaciones que coincidan» aunque las hubiera.

## Qué cambia

### 1. Reserva para autos nuevos (interruptor, sale apagado)

`app_config.trial_reserve = {"enabled": false, "backfill_max": 30}`. Se edita en `/admin/config`.

- **Prendida:** de los resultados de la prueba (`plan_limits.free.max_total_results`, 50), como máximo `backfill_max` son publicaciones que ya estaban. El resto queda para autos nuevos durante la prueba.
- **Apagada:** la regla de antes, sin cambios. Entra lo primero que aparece hasta llenar el cupo.
- **Valores rotos** (sin `backfill_max`, texto, negativo, `enabled` que no es `true`): apagada.
- **Quién la aplica:** la base, en el trigger `admit_free_result`. El worker no cambia.
- **Qué es «ya publicado»:** lo que el worker guardó como backfill, lo que el sistema vio antes de que existiera la búsqueda, o lo publicado hace más de `recommended_max_age_days` (15). Lo último cubre el stock viejo que un crawl lee por primera vez.
- **Nunca quita** un resultado ya admitido.
- **Al apagarla,** lo que quedó afuera puede entrar en el próximo re-score, como antes.
- **Con la reserva prendida, Planes y Términos** dicen cuántos de los 50 pueden ser ya publicados.
- **Aviso de zona:** con la reserva prendida, no ofrece ampliar más de lo que la prueba todavía admite de lo ya publicado.

`free_trial_results.is_backfill` guarda si cada resultado admitido era stock o nuevo. Se llena desde la migración, con el interruptor prendido o apagado, para tener datos al decidir. Lo admitido antes vale `null` y cuenta como stock.

### 2. Avisos de lo que la prueba oculta

El worker descarta, antes de repartir los avisos del día, los de publicaciones que la prueba oculta (`free_result_allowed` falso): nuevos, bajas de precio y bajas. Antes se encolaban, ocupaban lugar en el tope de 3 por día dentro de la misma tanda y después se salteaban al entregar. Para planes pagos no cambia nada.

### 3. Mails que cuentan lo que se ve

- **Bienvenida (`search_activated`):**
  - cuenta solo lo que la prueba muestra, en la búsqueda que más muestra;
  - dice cuántas más oculta;
  - nunca dice «Todavía no apareció ninguno» si hay coincidencias ocultas.
  - En lugar de «Te avisamos de los nuevos apenas aparezcan», dice cuántos resultados le quedan a la prueba, o que ya no le quedan.
- **Fin de prueba (`trial_ended`):** cuenta lo que la prueba mostró y suma «Hay N más que coincidían y tu prueba no mostraba: podés verlas con Particular.». N son solo coincidencias que siguen publicadas.
- **Oportunidad perdida:** «te hubiéramos avisado», sin «apenas apareció».
- Las cuentas sin cupo de prueba (pagas, piloto) reciben los mismos conteos que antes.

Los textos están en `docs/MAILS_DE_PLAN.md`.

### 4. Página de la búsqueda

- Si la lista está vacía y la prueba oculta coincidencias: «Hay N publicaciones que coinciden y tu prueba no muestra. Con Particular ves todas.»
- Con resultados: al final, «Y N más que coinciden y tu prueba no muestra.»
- Con la prueba llena y nada oculto: «Tu prueba ya usó sus 50 resultados: con Particular te avisamos de las nuevas.»
- Con coincidencias ocultas no aparece la tarjeta del bot de pocos resultados: el problema no es la zona ni los filtros.
- El cartel de preparación ya no promete «cada auto nuevo» en la prueba. Dice que los mejores llegan en el momento y otros en el resumen diario, o que la prueba ya no avisa.
- `my_search_hidden_results(id)` cuenta las coincidencias ocultas de una búsqueda propia, solo publicaciones activas.

## Qué queda afuera

- **Lemas de marca y SEO** («Te avisamos cuando aparezca» en la portada, metadatos, guías): no son de la prueba.
- **Mails de los 7 días extra** (`bonus_*`): vienen apagados. Si se prenden, revisar sus conteos.
- **«Solo los mejores» del día entero:** el tope de 3 avisos por día ya existe y elige por nivel y puntaje dentro de cada tanda. Elegir los mejores del día obligaría a retener avisos.
- **Búsquedas sin modelo:** lo que el enriquecimiento completa después cuenta como stock aunque sea nuevo (conservador).

## Despliegue

1. Migración `20261207120000_trial_reserve.sql`, a mano con el OK de Juan: transacción más el insert de la versión exacta; antes, ver `max(version)` en prod.
2. Merge: Vercel publica la web.
3. Worker en el VPS: los mails nuevos y el filtro de avisos ocultos.

Sin el worker, la web anda igual. Sin la migración, la página cuenta 0 ocultas y el interruptor no existe.

## Encender la reserva

Desde el 11/11 a las 13:11 UTC, después de leer la medición del aviso de zona (`docs/AVISO_ZONA.md`). Se prende en `/admin/config`, `trial_reserve.enabled = true`, y el cambio queda en el historial.

Para medirla, comparar las cuentas que empiezan la prueba después de prenderla contra las de antes:

- pruebas llenas en la primera hora;
- avisos inmediatos de autos nuevos durante la prueba;
- `free_trial_results.is_backfill`.
