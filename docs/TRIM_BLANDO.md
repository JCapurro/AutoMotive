# Trim blando: otra versión no alerta

Decisión de Juan, 2026-11-24 (opción A de `docs/PLAN_CORRECCION_AUDITORIAS_2026-11-24.md`, punto 1).

## Qué hace

Si una búsqueda **nombra versión** (`filters.trims` no vacío) y **no es estricta** (`trim_strict` falso), un auto de **otra versión** (el componente `trim` da `FAIL` / «otra versión») no alerta: su nivel máximo es `match` (🟡). Con `notify_min_level` en `good` (el valor de siempre), el motor de notificaciones no lo manda.

- **Sigue visible** en la lista. Con el orden por defecto (`score`) va después de todos los de la versión pedida (cada grupo ordenado por score), y la tarjeta muestra la etiqueta corta «Otra versión» junto al nombre.
- **No se toca** una versión desconocida (`trim` nulo: el componente da «desconocido», no «otra versión»), una búsqueda estricta (ya filtra, nada cambia) ni una versión que solo viene de `preferences.preferred_trims` (un gusto, no la versión pedida).
- El score no cambia (sigue siendo el mismo número, para ordenar); solo el nivel. Si otro tope ya lo dejaba más abajo, se queda donde estaba.
- **f3 (sombra)**: el tope aplica al f2 que decide y f3 lo refleja sin cambiar su modo: `score_breakdown.shadow_f3.level` también queda en `match` y `shadow_f3.trim.capped` dice si el tope movió su nivel (`level_uncapped` guarda el de antes). `mode`, `params` y la medición de la sombra no se tocan.

Dónde: `worker/intelligence/matching.py` (`other_trim_soft`), `scoring.py` (el tope y `score_breakdown.trim_cap`), `f3.py` (`trim_cap`), `config.py` (`trim_soft_cap`), `supabase/migrations/20270113120000_trim_soft_cap.sql` (la fila y el orden de `search_results`), `web/lib/other-version.ts` y `web/components/app/listing-card.tsx` (la etiqueta).

## Interruptor y vuelta atrás

`app_config.trim_soft_cap = {"enabled": false}`: **apagado** al migrar (inerte: nada cambia hasta prenderlo). Se prende y se apaga en `/admin/config` sin deploy.

- Prendido: los matches nuevos salen con el tope; los ya guardados lo toman en el próximo rescore nocturno (`rescore.hour`), sin subir `SCORING_VERSION`. Para aplicarlo antes a las búsquedas con versión, se puede forzar un rescore.
- Apagado: vuelve todo como estaba (nivel, alerta y orden) con el próximo rescore. La marca `trim_cap` de un match viejo desaparece cuando se vuelve a puntuar.
- Un alerta ya mandada no se retira.

## Cómo medirlo (solo lectura)

Objetivo: de las alertas enviadas en búsquedas que piden versión, menos de 10 % de otra versión (hoy 42–47 % de los `good`/`high`). Y que las búsquedas no pasen a tener menos de 4 resultados.

```sql
-- % de alertas enviadas (new_match y opportunity) de otra versión, por semana,
-- en búsquedas que piden versión sin exigirla. Cambiar `since` por el día de encendido.
select date_trunc('week', n.created_at)::date                         as semana,
       count(*)                                                       as enviadas,
       count(*) filter (where m.match_reasons -> 'trim' ->> 'result' = 'fail') as otra_version,
       round(100.0 * count(*) filter (where m.match_reasons -> 'trim' ->> 'result' = 'fail') / count(*), 1) as pct
  from public.notifications n
  join public.matches m          on m.id = n.match_id
  join public.search_profiles sp on sp.id = m.search_profile_id
 where n.kind in ('new_match', 'opportunity')
   and n.status = 'sent'
   and n.created_at >= timestamptz '2026-11-09'
   and jsonb_typeof(sp.filters -> 'trims') = 'array' and sp.filters -> 'trims' <> '[]'::jsonb
   and coalesce((sp.filters ->> 'trim_strict')::boolean, false) = false
 group by 1 order by 1;

-- Cuántas búsquedas con versión quedan con menos de 4 resultados visibles (mirar antes y después de prender).
select count(*) filter (where c.n < 4) as con_menos_de_4, count(*) as busquedas
  from public.search_profiles sp
  left join lateral (select count(*) n from public.matches m
                       join public.listings l on l.id = m.listing_id
                      where m.search_profile_id = sp.id and l.status = 'active') c on true
 where sp.enabled
   and jsonb_typeof(sp.filters -> 'trims') = 'array' and sp.filters -> 'trims' <> '[]'::jsonb
   and coalesce((sp.filters ->> 'trim_strict')::boolean, false) = false;

-- Cuántos matches están hoy con el tope (otra versión que habría sido good/high).
select count(*) from public.matches where score_breakdown ->> 'trim_cap' = 'true';
```

Para el antes/después de f3: `select f3 -> 'trim' ->> 'capped', count(*) from public.match_decisions where decided_at >= … group by 1`.

Limitación: las alertas sin `match_id` (18–23 % de los `new_match`, punto 5 del plan) no se pueden clasificar con esta consulta.

## Pruebas

- Worker: `worker/tests/test_trim_soft_cap.py` (interruptor, función compartida, tope en f2, f3, alerta).
- Web: `web/lib/other-version.test.ts` (etiqueta) y `web/lib/admin-config.test.ts` (validador del interruptor).
- pgTAP: `supabase/tests/trim_soft_cap_test.sql` (fila apagada y orden de `search_results`).
