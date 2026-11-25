# Duplicados, precios placeholder y avisos terminados

Punto 3 de `PLAN_CORRECCION_AUDITORIAS_2026-11-24.md`. Todo sale **apagado**: tres interruptores en `app_config.listing_noise`
(migración `20270113120000_listing_noise_switches.sql`, solo una fila). Sin la fila, o con cualquier valor que no sea `true`, están apagados.

## Por qué no se juntaban los reposteos

`intelligence/duplicates.py` y `listing_duplicates` son otra cosa: detectan el mismo auto entre **fuentes** o por fotos (bandera de riesgo),
nunca agrupaban alertas. El vínculo `probable_repost_of` lo pone `find_repost_of` al insertar, **solo con huella** (`listings.fingerprint`).
Y la huella exige make, model, year **y km**: el 77 % de los avisos activos de Facebook (9.612 de 12.440, 24/11) no tiene km, así que no tiene huella
ni vínculo. Los Golf a USD 11.111 son del mismo vendedor (o cuentas parecidas) y sin km; el Cronos «con gnc» son 4 copias de un vendedor con
distinta localidad (la huella incluye la localidad). Además la regla «re-publicado» de `engine.py` solo **rotula** el aviso: igual se enviaba.

## Qué hace cada interruptor

| Clave | Efecto |
|---|---|
| `repost_groups` | Una alerta por auto. En `notifications/service._commit` (antes de `decide_all`): (1) un match nuevo cuyo usuario ya recibió una alerta `new_match`/`opportunity` de un gemelo no alerta; (2) de los gemelos de un mismo lote solo alerta el mejor (nivel, luego score); los demás quedan como matches del grupo. Gemelo = misma huella, o vínculo `probable_repost_of`, o **mismo vendedor no-agencia** en la misma fuente con misma marca/modelo/año, precio a ≤ 3 % y km sin contradicción (uno sin km no contradice). Los precios de agencias no se agrupan: dos unidades iguales de un stock son dos autos (45 de 52 casos que solo esta cláusula encontraba eran de agencias). La regla «re-publicado» sigue: un reposteo de un auto que ese usuario nunca recibió se alerta con el rótulo, como antes. |
| `placeholder_f2` | f2 trata el precio placeholder (un dígito 1–8 repetido 4+ veces, `f3.placeholder_price`) como «sin precio»: sin crédito de precio (no hay `price_ref`, no puede alcanzar un umbral Pro) y nivel tope `match` (`guard: placeholder` en el desglose). Un anticipo excluido sigue excluido. f3 no cambió: su sombra lee el mismo puntaje f2 de siempre (test). |
| `ended_guard` | No se crea alerta `new_match`/`opportunity`/`price_drop` de un aviso que ya no está `active`. `listing_gone` no se toca. |

**Lista del usuario:** ya filtra `listing_status = 'active'` en «todos», «nuevos», «oportunidades», los contadores y `recent_opportunities`
(`search_results`, 20261130120000). Las pestañas guardados/contactados/visita/comprados muestran terminados a propósito (historial). No hay hueco
que cerrar en la lista; los «terminados en el top 10» de las auditorías salen de la tabla `matches` cruda (ver medición). El hueco real eran las alertas.

## Cómo prenderlo y apagarlo (sin deploy)

```sql
-- prender de a uno, con tu OK
update public.app_config set value = value || '{"placeholder_f2": true}' where key = 'listing_noise';
-- apagar todo
update public.app_config set value = '{}' where key = 'listing_noise';
```

El worker lee la fila con la caché de `db.get_config`. `placeholder_f2` actúa cuando un match se puntúa (nuevos y re-scores); los otros dos, en el
siguiente lote de alertas. Si la lectura falla, quedan apagados. No hay dato de cuándo se refresca la caché ni de si el re-score actualiza los
matches viejos con placeholder: verificarlo al prenderlo.

## Cómo medir

`docs/sql/medir_ruido_de_avisos.sql` (solo lectura; cambiar `:desde`):
1. avisos repetidos por 100 enviados por huella; 2. lo mismo con la regla de grupos; 3. avisos terminados en los 10 mejores (tabla `matches`); 4. alertas con placeholder por nivel.

Base desde el 09/11 (producción, 24/11): 1.981 envíos (usuario, aviso) → 60 repetidos por huella (3,0 por 100) y 71 por la regla de grupos (3,6 por 100);
17 envíos con precio placeholder; 38 de 718 filas del top 10 de `matches` están terminadas (22 de Facebook, 5,3 %), 0 en lo que ve el usuario.
Objetivo con los interruptores prendidos: repetidos por grupo → casi 0 desde la fecha de prendido; envíos con placeholder en `good`/`high` → 0.
Los 38 «terminados entre los enviados» son avisos que terminaron *después* de alertarse; `ended_guard` no los puede evitar.

## No verificado

- Falsos positivos de la regla de grupos (un vendedor particular con dos autos iguales al mismo precio): no hay forma de medirlo sin etiquetar a mano.
- No se miró el efecto en producción: nada prendido ni aplicado. La migración solo se aplicó en la base local de pruebas.
- pgTAP (`supabase/tests/listing_noise_test.sql`) no se corrió: los clones locales no tienen pgtap.
- El validador de `/admin/config` no conoce `listing_noise`; hoy se edita por SQL.
