# Auditoría de matches: regla, muestreo y consultas

Para repetir la auditoría del 07/11 y del 24/11 con el mismo criterio y comparar semana a semana. Origen: `docs/PLAN_CORRECCION_AUDITORIAS_2026-11-24.md`. La pantalla de revisión manual es `/admin/matches/audit` (muestra de 60, `admin_match_reviews`).

## 1. Veredicto por búsqueda

Se juzgan los **10 mejores matches** de la búsqueda (orden de la lista del usuario: puntaje descendente). Un match «encaja» si es el auto que la búsqueda pide: marca, modelo, versión (si la pide), año, km, precio, zona, transmisión, combustible.

| Veredicto | Regla |
|---|---|
| **Bien** | 70 % o más de los 10 mejores encajan **y** no hay basura (repuestos, avisos terminados, precios placeholder, reposteos del mismo auto). |
| **Regular** | Entre 40 % y 70 % encajan. |
| **Mal** | Menos de 40 % encajan, **o** la basura domina la lista. |
| **Sin resultados** | La búsqueda no tiene ningún match: **cuenta como mala para el usuario** (aparte, ver §2). |

Con menos de 10 matches se juzgan los que haya (el porcentaje es sobre esos). Razones posibles por match: versión distinta, zona, precio, año, no es un auto, repetido, ya terminó, otra (las mismas de la pantalla).

### Juzgar contra los filtros finales

Los usuarios editan sus búsquedas (38 de las 60 de la muestra del 24/11). Se juzga **siempre contra los filtros que la búsqueda tiene hoy**, nunca contra lo que el usuario escribió primero. Un auto que encaja con los filtros finales pero no con el pedido original no es un error del sistema. Para saber si un filtro cambió a propósito: el evento `search_profile_updated` guarda desde este cambio `props.previous_filters` (valor anterior de cada filtro que cambió), `changed_keys`, `zone_changed` y `preferences_changed`; antes del cambio solo tiene `filters_changed`. `search_profile_created.props.edited` dice si el usuario retocó lo que propuso el asistente.

## 2. Muestreo

- **Fecha fija**: se elige una fecha de corte a las 03:00 UTC (medianoche argentina) y se registra en el informe. Entran las búsquedas creadas desde esa fecha (24/11: `2026-11-09 03:00 UTC`). No se cambia a mitad de una serie.
- **Al azar y repetible**: ordenar por `md5(id::text)` y tomar 60. Mismo corte, misma muestra.
- **Solo búsquedas con al menos un match**; las que no tienen ninguno se cuentan aparte y se suman al resultado como malas.
- Excluir cuentas de admin y de prueba si el corte las incluye.

```sql
-- Muestra de 60 búsquedas con match, y conteo aparte de las que no tienen (cambiar el corte)
with since as (select timestamptz '2026-11-09 03:00:00+00' t),
s as (select sp.id from public.search_profiles sp, since where sp.created_at >= since.t),
withm as (select id from s where exists (select 1 from public.matches m where m.search_profile_id = s.id))
select (select count(*) from s)                                   as searches_since,
       (select count(*) from withm)                               as with_match,
       (select count(*) from s) - (select count(*) from withm)    as without_match;

select id from (select id from withm) w order by md5(id::text) limit 60;  -- la muestra

-- Los 10 mejores matches de una búsqueda de la muestra
select m.id, m.score, m.level, l.source, l.title, l.year, l.price_usd
  from public.matches m join public.listings l on l.id = m.listing_id
 where m.search_profile_id = :id order by m.score desc, m.id limit 10;
```

## 3. Consultas de la repetición del 24/11 (solo SELECT)

Todas se corren con el mismo corte (`2026-11-09 03:00 UTC`). Valores del 24/11 entre paréntesis. Las pesadas que mezclan fuentes se corren de a una fuente para no agotar el tiempo.

### 3.1 Matches de otra versión en búsquedas que piden versión (50,1 %)

`score_breakdown->'trim'->>'c'` es la compatibilidad de versión (1 = la pedida); menos de 0,5 = otra versión.

```sql
with ver as (
  select (m.score_breakdown->'trim'->>'c')::numeric c
    from public.matches m join public.search_profiles sp on sp.id = m.search_profile_id
   where jsonb_array_length(coalesce(sp.filters->'trims', '[]'::jsonb)) > 0
     and m.score_breakdown->'trim' ? 'c'
     and m.generated_at >= timestamptz '2026-11-09 03:00:00+00')
select count(*) as asks_version, count(*) filter (where c < 0.5) as other_version,
       round(100.0 * count(*) filter (where c < 0.5) / nullif(count(*), 0), 1) as pct_other_version
  from ver;   -- 13.249 / 6.641 / 50,1
```

Para separar blandas de estrictas, agregar `and (sp.filters->>'trim_strict')::boolean is not true` (con `trim_strict` el filtro funciona: 2 de 1.273).

### 3.2 Basura de Facebook por título (2 de 499 enviados)

```sql
with sent as (
  select distinct n.search_profile_id sp, n.listing_id
    from public.notifications n
   where n.kind::text in ('new_match', 'opportunity') and n.status::text = 'sent'
     and n.created_at >= timestamptz '2026-11-09 03:00:00+00' and n.search_profile_id is not null)
select count(*) filter (where l.title ~* '\m(espejo|faro|optica|óptica|paragolpes?|butacas?|puerta|capot|motor|caja|llantas?|repuestos?|sold|vendido)\M') as junk_title,
       count(*) as fb_sent
  from sent s join public.listings l on l.id = s.listing_id
 where l.source = 'facebook';
```

La lista de palabras es la de `price_partial_reason like 'no es un auto: título: …'`; actualizarla con ese motivo si aparecen otras.

### 3.3 Oportunidades enviadas con menos de 15 % de descuento (234 de 360 = 65,0 %)

`shadow_f3.deal.diff_pct` es el descuento que ve f3 (en sombra).

```sql
select count(*) as opportunities_sent,
       count(*) filter (where (m.score_breakdown->'shadow_f3'->'deal'->>'diff_pct')::numeric < 15) as under_15,
       round(100.0 * count(*) filter (where (m.score_breakdown->'shadow_f3'->'deal'->>'diff_pct')::numeric < 15)
             / nullif(count(*) filter (where m.score_breakdown->'shadow_f3'->'deal'->>'diff_pct' is not null), 0), 1) as pct
  from public.notifications n join public.matches m on m.id = n.match_id
 where n.kind::text = 'opportunity' and n.status::text = 'sent'
   and n.created_at >= timestamptz '2026-11-09 03:00:00+00';
```

Ojo: los mails sin `match_id` quedan fuera de esta consulta (ver 3.4).

### 3.4 Mails sin match (196 de 1.147 = 17,1 %; `new_match` 153 de 743)

```sql
select n.kind::text, count(*) as sent, count(*) filter (where n.match_id is null) as no_match,
       round(100.0 * count(*) filter (where n.match_id is null) / count(*), 1) as pct
  from public.notifications n
 where n.kind::text in ('new_match', 'opportunity') and n.status::text = 'sent'
   and n.created_at >= timestamptz '2026-11-09 03:00:00+00'
 group by 1;

-- Cuántos de esos mails siguen a una edición de filtros después del envío
select count(*) from public.notifications n
 where n.kind::text in ('new_match', 'opportunity') and n.status::text = 'sent' and n.match_id is null
   and n.created_at >= timestamptz '2026-11-09 03:00:00+00'
   and exists (select 1 from public.events e
                where e.name = 'search_profile_updated' and (e.props->>'profile_id')::bigint = n.search_profile_id
                  and (e.props->>'filters_changed') = 'true' and e.created_at > n.sent_at);   -- 21
```

El desglose por causa está en `docs/INFORME_MAILS_SIN_MATCH_2026-11-24.md`. Desde que el evento guarda `previous_filters`, se puede ver qué cambió.

### 3.5 Avisos repetidos por huella (29 de 1.146 avisos enviados)

```sql
with sent as (
  select distinct n.search_profile_id sp, n.listing_id
    from public.notifications n
   where n.kind::text in ('new_match', 'opportunity') and n.status::text = 'sent'
     and n.created_at >= timestamptz '2026-11-09 03:00:00+00' and n.search_profile_id is not null),
j as (select s.sp, l.fingerprint from sent s join public.listings l on l.id = s.listing_id)
select (select count(*) from j) as sent_listings,
       (select coalesce(sum(c - 1), 0)
          from (select count(*) c from j where fingerprint is not null group by sp, fingerprint having count(*) > 1) g) as repeated_by_fingerprint;
```

(La repetición del 24/11 contó 15 de 325 y 12 de 425 en dos períodos de Facebook; esta consulta cuenta todas las fuentes y todos los envíos del corte.)

## 4. Cómo repetirla

1. Elegir el corte (03:00 UTC) y anotarlo. Correr §2 y revisar a mano las 60 búsquedas en `/admin/matches/audit` o con los 10 mejores de cada una.
2. Poner el veredicto de §1 contra los filtros finales. Sumar las búsquedas sin resultados como malas.
3. Correr §3 y comparar con los valores de arriba. Re-medir a los 7 días de cada despliegue del plan.
4. Quien revisó queda registrado en `admin_match_reviews.reviewer_id` y `reviewer_kind` (`person` = guardado desde la pantalla; `automated` = guardado por un script; vacío = no se sabe). Una revisión automática sirve para priorizar, no reemplaza el veredicto de una persona.
