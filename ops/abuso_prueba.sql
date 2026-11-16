-- ¿Se repite la prueba gratis de 72 h con otro mail? Solo lectura. Correr en el
-- editor SQL de Supabase (necesita leer auth.users). Tres consultas independientes.
--
-- Señales disponibles hoy: el mail y la búsqueda. La IP no sirve para mirar hacia
-- atrás: auth_throttle guarda un hash sin user_id y lo borra a los 2 días.
--
-- Cómo leer la 3: los pares de búsquedas casi idénticas que arrancan DURANTE la
-- prueba anterior son casi todos coincidencias (nadie necesita otra cuenta si la
-- suya sigue activa): eso es la línea de base. Si hubiera abuso, la franja de
-- «0 a 7 días tras vencer» tendría muchos más pares por día que esa base.

-- 1. Resumen de pruebas
select count(*) filter (where free_trial_started_at is not null) pruebas,
       count(*) filter (where free_trial_started_at is not null and email_only) pruebas_solo_mail,
       count(*) filter (where plan <> 'free') pagos_activos
  from public.profiles;

-- 2. Mismo mail con otra forma (alias +, puntos de Gmail) y dominios descartables
with t as (
  select lower(u.email) email, split_part(lower(u.email), '@', 2) dom
    from public.profiles p join auth.users u on u.id = p.id
   where p.free_trial_started_at is not null
), c as (
  select *, case when dom in ('gmail.com', 'googlemail.com')
                 then replace(split_part(split_part(email, '@', 1), '+', 1), '.', '') || '@gmail.com'
                 else split_part(split_part(email, '@', 1), '+', 1) || '@' || dom end canon
    from t
)
select count(*) pruebas,
       count(*) - count(distinct canon) pruebas_extra_mismo_mail_canonico,
       count(*) filter (where email like '%+%@%') con_alias_mas,
       count(*) filter (where dom ~ '(mailinator|tempmail|temp-mail|10minute|guerrilla|yopmail|sharklasers|trashmail|dispostable|getnada|maildrop|mohmal|emailondeck|fakeinbox|throwaway|mailnesia|tmpmail|minuteinbox|burner)') descartables,
       count(*) filter (where dom not in ('gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'yahoo.com.ar',
                                          'live.com', 'live.com.ar', 'icloud.com', 'hotmail.com.ar', 'outlook.com.ar')) dominios_raros
  from c;

-- 3. La misma búsqueda desde otra cuenta: marca, modelo, mismo punto (~1 km),
--    mismo radio, mismo año mínimo y precio máximo ±10 %.
with s as (
  select distinct p.id uid, p.free_trial_started_at ts,
         lower(sp.filters ->> 'make') mk, lower(coalesce(sp.filters ->> 'model', '')) md,
         nullif(sp.filters ->> 'year_min', '')::int ymin, nullif(sp.filters ->> 'price_max', '')::numeric pmax,
         coalesce(sp.filters ->> 'currency', '') cur,
         round(sp.origin_lat::numeric, 2) lat, round(sp.origin_lon::numeric, 2) lon, sp.radius_km rad
    from public.profiles p join public.search_profiles sp on sp.user_id = p.id
   where p.free_trial_started_at is not null and sp.filters ->> 'make' is not null and sp.origin_lat is not null
), pares as (
  select a.uid a, b.uid b, b.ts - a.ts gap
    from s a join s b
      on a.mk = b.mk and a.md = b.md and a.lat = b.lat and a.lon = b.lon and a.uid <> b.uid and b.ts > a.ts
     and a.ymin is not distinct from b.ymin and a.rad is not distinct from b.rad
     and (a.pmax is not distinct from b.pmax
          or (a.cur = b.cur and abs(a.pmax - b.pmax) <= 0.1 * greatest(a.pmax, b.pmax)))
)
select case when gap < interval '72 hours' then '1 durante la prueba anterior (3 días, base)'
            when gap < interval '10 days'  then '2 de 0 a 7 días tras vencer (7 días)'
            else '3 más de 7 días tras vencer' end franja,
       count(*) pares, count(distinct b) cuentas_sospechosas
  from pares group by 1 order by 1;
