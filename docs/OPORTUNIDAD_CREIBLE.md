# Oportunidad creíble: 🔥 solo con descuento real

Decisión de Juan, 2026-11-24: umbral 15 % (punto 2 de `docs/PLAN_CORRECCION_AUDITORIAS_2026-11-24.md`).

## Qué hace

Hoy un aviso es `opportunity` cuando el match es `high`. Con el interruptor prendido, `opportunity` exige además:

- **descuento creíble**: `diff_pct` de al menos `min_pct` (15), el que ya calcula f2 y el mismo número que guarda `score_breakdown.shadow_f3.deal.diff_pct` (viaja en `payload.match.diff_pct`);
- **comparables suficientes**: `n >= min_n` (10), de `payload.match.price_ref.n`.

Lo que no llega sigue alertando **como `new_match`**, con el texto de siempre. No se pierde ninguna alerta: mismo destinatario, mismos canales, misma clave de dedupe (`match:<listing_id>`), mismo tope diario y mismo digest; solo cambia el tipo. Sin `diff_pct` o sin `n` (precio sin comparables) no se puede probar y también va como `new_match`. Un re-publicado ya era `new_match`.

**Umbrales Pro (`opportunity_threshold_pct` / `opportunity_threshold_usd`): no cambian.** Un aviso que alcanza el umbral de la propia búsqueda sigue saliendo fuera del tope diario y conserva su tipo de siempre (`opportunity` si el match es `high`): es la definición de oportunidad de ese usuario. Lo que no alcanza su umbral sigue yendo al digest.

Regla en la cabecera de `worker/notifications/engine.py` (tabla de 7.1) y en `classify`/`credible_opportunity`.

## Interruptor y vuelta atrás

`app_config.opportunity_gate = {"enabled": false, "min_pct": 15, "min_n": 10}` (migración `20270115120100_opportunity_gate.sql`): **apagado** al migrar; inerte hasta prenderlo en `/admin/config`. Apagarlo vuelve al comportamiento anterior al próximo lote de avisos, sin deploy. Los avisos ya enviados no se tocan. El worker lee la fila en cada lote (`notifications.service.load_rules`); una clave faltante o mala toma su valor por defecto.

## Qué no cambia

- Quién recibe el aviso, cuándo y cuántos por día (el tope y el digest no miran el tipo).
- La lista de la web y el filtro «Oportunidades» siguen usando `level = high` (no es un aviso). Si Juan quiere alinearlo con el aviso, es otro cambio.
- La columna `match_decisions.f3_kind` (la sombra de f3) se calcula con las reglas por defecto, sin el filtro: compara «qué habría sido con f3» sin este cambio. `f2_kind` sí lo refleja.

## Cómo medirlo (solo lectura)

Objetivo: oportunidades enviadas con menos de 15 % de descuento = 0 (hoy 65 %), y ver cuántas oportunidades por semana quedan.

```sql
-- % de oportunidades enviadas con menos del umbral (o sin descuento / pocos comparables), por semana.
-- Excluye las que alcanzaron un umbral Pro de la propia búsqueda (payload.threshold_pct / threshold_usd).
select date_trunc('week', n.created_at)::date as semana,
       count(*)                                                                  as oportunidades,
       count(*) filter (where coalesce((n.payload -> 'match' ->> 'diff_pct')::numeric, -1) < 15) as menos_de_15,
       count(*) filter (where coalesce((n.payload -> 'match' -> 'price_ref' ->> 'n')::int, 0) < 10) as menos_de_10_comparables,
       round(100.0 * count(*) filter (where coalesce((n.payload -> 'match' ->> 'diff_pct')::numeric, -1) < 15) / count(*), 1) as pct_menos_de_15
  from public.notifications n
 where n.kind = 'opportunity'
   and n.status = 'sent'
   and n.channel = 'email'                     -- una por aviso (el mismo aviso va por varios canales)
   and not (n.payload ? 'threshold_pct' or n.payload ? 'threshold_usd')
   and n.created_at >= timestamptz '2026-11-09'
 group by 1 order by 1;

-- Cuántos avisos new_match salieron de un high que no llegó (para ver que no se perdió ninguno):
-- comparar el total de avisos (new_match + opportunity) por semana antes y después de prenderlo.
select date_trunc('week', created_at)::date as semana, kind, count(*)
  from public.notifications
 where kind in ('new_match', 'opportunity') and status = 'sent' and channel = 'email'
   and created_at >= timestamptz '2026-11-09'
 group by 1, 2 order by 1, 2;
```

Limitación: las alertas de un solo canal que no sea email no entran en la primera consulta; cambiar `channel` para medir otro. El total de avisos no debería bajar al prenderlo (solo se mueve de `opportunity` a `new_match`).

## Pruebas

- Worker: `worker/tests/test_opportunity_gate.py` (configuración, tabla con el filtro, ningún aviso perdido, tope y digest, umbrales Pro).
- Web: `web/lib/admin-config.test.ts` (validador de la fila).
- pgTAP: `supabase/tests/opportunity_gate_test.sql`.
