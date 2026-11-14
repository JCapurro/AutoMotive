# Aviso de auto cerca de la zona

Juan, 14/11/2026. Un email que muestra un auto nuevo que cumple todos los filtros de una búsqueda menos la zona. La búsqueda no se amplía sola: la persona ve el auto y decide.

## Por qué

Medido el 14/11/2026 en producción: de 480 cuentas con una búsqueda, 91 no tenían ningún resultado, y en 58 el bloqueo principal era la zona. El [aviso de zona](AVISO_ZONA.md) vive en la web y depende de que la persona vuelva (24 ampliaron). Este llega por email.

## Cuándo sale

- Su interruptor está prendido: `app_config.near_zone.enabled` es `true`. Nace apagado.
- La búsqueda está activa, con acceso, lista (`bootstrapped_at`, sin `rematch_requested_at`), tiene marca y modelo, y una sola zona propia (origen y radio, sin `extra_locations`).
- Tiene email entre sus canales.
- Muestra `max_results` resultados o menos (3), contados como el bot de pocos resultados.
- No recibió otro aviso de estos en los últimos `cooldown_days` días (3).
- Su dueño no dejó esa zona así con «Dejar así» del aviso de zona.
- Es horario de envío en Argentina (`send_from` a `send_until`, 09:00 a 21:00).

## Qué auto

Entre las publicaciones activas de esa marca y modelo:

- vista por primera vez después de crear la búsqueda, y publicada hace `max_age_days` días o menos (3);
- con precio completo y coordenadas;
- que solo falla el filtro de zona (`intelligence/matching.evaluate`): el resto pasa igual que en un resultado;
- a `max_extra_km` km o menos del borde de la zona (100).

Si hay varias, se elige la más cercana. Una publicación se avisa una sola vez por búsqueda (`near_zone_notices`).

## El email

- Asunto: «Apareció un Ford Focus 2016 a 45 km de Laferrere». Sin nombre de lugar dice «de tu zona».
- Foto, modelo y precio publicado, con la plantilla de marca.
- «Está a 45 km de Laferrere. Tu búsqueda llega hasta 30 km, por eso no aparece entre tus resultados.»
- «Cumple el resto de tus filtros.»
- «Si te sirve, ampliá la zona de tu búsqueda y te avisamos de los próximos.»
- Botón «Ver la publicación» (el aviso original) y link «Ampliar la zona de mi búsqueda» (la página de la búsqueda).

## Límites conocidos

- El auto no pasa por el cupo de la prueba gratis: no es un resultado de la búsqueda y no gasta cupo.
- Los links no registran clics. Para medirlo: `near_zone_notices` con `status = 'sent'` contra los eventos `search_zone_widened` posteriores de la misma búsqueda.
- No es una fila de `notifications`: el embudo «Recibieron una alerta» del admin no lo cuenta.
- Un envío que falla queda `failed` y no se reintenta; la búsqueda espera su `cooldown_days` igual.
- Comparte la cuota de Resend con las alertas y los mails de plan, sin tope diario propio más que `max_per_tick` por pasada (cada 15 minutos).

## Código

- Migración [`20261218120000_near_zone_notice.sql`](../supabase/migrations/20261218120000_near_zone_notice.sql): la tabla y la fila de `app_config`.
- Worker: `intelligence/near_zone.py` (qué auto), `pipeline/near_zone.py` (la pasada), `notifications/near_zone.py` (el email), `db/repos/near_zone.py`.
- Tests: `worker/tests/test_near_zone.py`.
