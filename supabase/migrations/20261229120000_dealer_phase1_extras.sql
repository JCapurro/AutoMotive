-- Agencias, fase 1: lo que faltaba del panel de stock
-- (docs/PLAN_AGENCIAS_STOCK_Y_CANAL.md §3, fase 1; base en 20261228120000_dealer_program.sql).
--
-- Va después de 20261228120000_dealer_program.sql y no la edita. No agrega FK a `listings`
-- ni columnas a `listings`: no hace falta parar el worker, pero el worker nuevo (avisos y lectura
-- por foto) necesita esta migración aplicada. Aplicar a mano según la memoria de migraciones de
-- producción, con OK de Juan. Nada de esto se aplica en esta rama.
--
-- Qué agrega (todo apagado por defecto):
-- * dealer_program() con cuatro claves nuevas, saneadas igual que las otras (gemelos en
--   worker/intelligence/config.py y web/lib/dealer-program.ts):
--     alerts_enabled (bool, false)            avisos por email a la agencia
--     alerts_every_hours (6-168, 24)          tope de frecuencia: un resumen cada tantas horas
--     photo_import_enabled (bool, false)      carga por foto o PDF de la lista (cuesta por uso)
--     photo_import_daily_limit (1-50, 5)      lecturas por agencia y día (hora de Argentina)
--   La fila de app_config recibe las claves que le falten, con su valor por defecto.
-- * Avisos a la agencia: dealers.alerts_email (preferencia de la agencia, prendida por defecto;
--   el interruptor general manda), dealers.alerts_checked_at, dealer_set_alerts(),
--   dealer_alert_state (la referencia contra la que se compara cada auto) y dealer_alerts (cada
--   aviso una sola vez: dedup_key único por agencia). dealer_alert_scan() junta lo que el worker
--   necesita por auto; la demanda sale cruda solo hacia el worker (service role), que nunca avisa
--   menos de demand_min_count personas.
-- * Carga por foto o PDF: dealer_stock_reads (el archivo, solo service role; el worker borra los
--   bytes apenas los lee), kind 'dealer_stock_read' en llm_jobs, encolado solo por
--   dealer_request_stock_read() (interruptor, pertenencia, tipo, tamaño y tope diario por agencia
--   bajo lock de la agencia; además corre el tope por hora de llm_jobs). El cliente ya no puede
--   insertar ese kind directo.
-- * dealer_import_items() y dealer_imports.kind aceptan 'photo' y 'pdf'.
--
-- Rollback: volver a aplicar dealer_program() y dealer_import_items() de 20261228120000;
-- `alter table public.dealer_imports` con el check ('csv','xlsx') (borrando antes las filas photo/pdf);
-- drop de dealer_set_alerts, dealer_alert_scan, dealer_request_stock_read y de las tablas
-- dealer_alerts, dealer_alert_state, dealer_stock_reads; `alter table public.dealers drop column
-- alerts_email, drop column alerts_checked_at`; llm_jobs: borrar las filas 'dealer_stock_read', volver
-- al check de kinds y a la política "llm_jobs: enqueue own" de 20261205120000_par04_model_guides.sql;
-- quitar de app_config.dealer_program las cuatro claves nuevas.

set local lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- 1. Switches
-- ---------------------------------------------------------------------------

create or replace function public.dealer_program() returns jsonb
language sql stable security definer set search_path = '' as $$
  with raw as (
    select coalesce((select c.value from public.app_config c where c.key = 'dealer_program'), '{}'::jsonb) as v
  ), typed as (
    select case when jsonb_typeof(raw.v -> 'enabled') = 'boolean' then (raw.v ->> 'enabled')::boolean
                else false end as enabled,
           case when jsonb_typeof(raw.v -> 'channel_enabled') = 'boolean' then (raw.v ->> 'channel_enabled')::boolean
                else false end as channel_enabled,
           case when jsonb_typeof(raw.v -> 'manual_confirm_days') = 'number'
                then public.dealer_json_int(raw.v -> 'manual_confirm_days') end as days,
           case when jsonb_typeof(raw.v -> 'demand_min_count') = 'number'
                then public.dealer_json_int(raw.v -> 'demand_min_count') end as min_count,
           case when jsonb_typeof(raw.v -> 'alerts_enabled') = 'boolean' then (raw.v ->> 'alerts_enabled')::boolean
                else false end as alerts_enabled,
           case when jsonb_typeof(raw.v -> 'alerts_every_hours') = 'number'
                then public.dealer_json_int(raw.v -> 'alerts_every_hours') end as every_hours,
           case when jsonb_typeof(raw.v -> 'photo_import_enabled') = 'boolean'
                then (raw.v ->> 'photo_import_enabled')::boolean else false end as photo_enabled,
           case when jsonb_typeof(raw.v -> 'photo_import_daily_limit') = 'number'
                then public.dealer_json_int(raw.v -> 'photo_import_daily_limit') end as photo_limit
      from raw
  )
  select jsonb_build_object(
           'enabled', t.enabled,
           'channel_enabled', t.channel_enabled,
           'manual_confirm_days', case when t.days between 1 and 60 then t.days else 7 end,
           'demand_min_count', case when t.min_count between 3 and 50 then t.min_count else 3 end,
           'alerts_enabled', t.alerts_enabled,
           'alerts_every_hours', case when t.every_hours between 6 and 168 then t.every_hours else 24 end,
           'photo_import_enabled', t.photo_enabled,
           'photo_import_daily_limit', case when t.photo_limit between 1 and 50 then t.photo_limit else 5 end)
    from typed t
$$;

comment on function public.dealer_program() is
  'app_config.dealer_program sanitized: enabled, channel_enabled (booleans, default false), manual_confirm_days '
  '(1-60, default 7), demand_min_count (3-50, default 3), alerts_enabled (default false), alerts_every_hours '
  '(6-168, default 24), photo_import_enabled (default false), photo_import_daily_limit (1-50, default 5).';

-- The keys the row lacks, with their defaults (what is there stays).
update public.app_config
   set value = '{"alerts_enabled": false, "alerts_every_hours": 24, "photo_import_enabled": false, "photo_import_daily_limit": 5}'::jsonb
               || value
 where key = 'dealer_program' and jsonb_typeof(value) = 'object';

-- ---------------------------------------------------------------------------
-- 2. Alerts for the agency
-- ---------------------------------------------------------------------------

alter table public.dealers
  add column alerts_email boolean not null default true,
  add column alerts_checked_at timestamptz;

-- The reference each car is compared against: the market median when we last
-- told the agency (or first saw it), the demand high-water mark, and since when
-- a cheaper look-alike counts as new.
create table public.dealer_alert_state (
  item_id           bigint primary key references public.dealer_stock_items (id) on delete cascade,
  market_median_usd numeric check (market_median_usd > 0),
  market_n          integer check (market_n >= 0),
  market_at         timestamptz,
  demand_searches   integer check (demand_searches >= 0),
  demand_people     integer check (demand_people >= 0),
  demand_at         timestamptz,
  cheaper_since     timestamptz,
  updated_at        timestamptz not null default now()
);

-- Each alert once (dedup_key per dealer). sent_at null = waiting for the next summary.
create table public.dealer_alerts (
  id         bigint generated always as identity primary key,
  dealer_id  bigint not null references public.dealers (id) on delete cascade,
  item_id    bigint references public.dealer_stock_items (id) on delete cascade,
  kind       text not null check (kind in ('market_moved', 'cheaper_nearby', 'slow', 'new_demand')),
  dedup_key  text not null check (char_length(dedup_key) between 3 and 200),
  payload    jsonb not null default '{}' check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  sent_at    timestamptz,
  unique (dealer_id, dedup_key)
);
create index dealer_alerts_pending_idx on public.dealer_alerts (dealer_id, id) where sent_at is null;
create index dealer_alerts_item_idx on public.dealer_alerts (item_id) where item_id is not null;

create trigger dealer_alert_state_updated_at before update on public.dealer_alert_state
  for each row execute function public.set_updated_at();

alter table public.dealer_alert_state enable row level security;
alter table public.dealer_alerts enable row level security;
revoke all on public.dealer_alert_state, public.dealer_alerts from public, anon, authenticated;
grant all on public.dealer_alert_state, public.dealer_alerts to service_role;

-- The agency's own preference: whether it wants the alerts email.
create function public.dealer_set_alerts(p_on boolean) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
begin
  if p_on is null then
    raise exception 'invalid_dealer:alerts_email' using errcode = 'P0001';
  end if;
  update public.dealers set alerts_email = p_on where id = v_dealer;
end $$;

-- What the worker needs per car on sale of one dealer to decide its alerts:
-- the market reference (dealer_market_ref), how long the model takes to sell,
-- days in stock, the raw demand that accepts it in the dealer's zone (only an
-- approved dealer; the worker never tells fewer than demand_min_count people),
-- the cheapest look-alike seen for the first time after `cheaper_since` within
-- p_radius_km that asks at least p_cheaper_pct % less, and the saved state.
-- Same pool as dealer_market_ref (every source but 'directo'), plus coordinates.
create function public.dealer_alert_scan(p_dealer_id bigint, p_cheaper_pct numeric default 8,
                                         p_radius_km numeric default 30)
returns table (item_id bigint, listing_id bigint, make text, model text, "trim" text, year integer,
               mileage_km integer, price numeric, currency text, price_usd numeric,
               market jsonb, model_days jsonb, days_in_stock integer, demand jsonb, cheaper jsonb, state jsonb)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_d       public.dealers;
  v_blue    numeric := public.dealer_blue_rate();
  v_members uuid[];
begin
  select d.* into v_d from public.dealers d where d.id = p_dealer_id;
  if v_d.id is null then
    return;
  end if;
  select coalesce(array_agg(m.user_id), '{}'::uuid[]) into v_members
    from public.dealer_members m where m.dealer_id = p_dealer_id;

  return query
  with base as (
    select i.id as b_item_id, l.id as b_listing_id, i.created_at as b_created_at,
           case when l.id is not null then l.make else i.make end as b_make,
           case when l.id is not null then l.model else i.model end as b_model,
           case when l.id is not null then l.trim else i.trim end as b_trim,
           case when l.id is not null then l.year else i.year end as b_year,
           case when l.id is not null then l.mileage_km else i.mileage_km end as b_km,
           case when l.id is not null then l.price else i.price end as b_price,
           case when l.id is not null then l.currency else i.currency end as b_currency,
           coalesce(l.source, 'directo') as b_source,
           coalesce(i.in_stock_since,
                    (l.published_at at time zone 'America/Argentina/Buenos_Aires')::date,
                    (i.created_at at time zone 'America/Argentina/Buenos_Aires')::date) as b_since
      from public.dealer_stock_items i
      left join public.listings l on l.id = i.listing_id
     where i.dealer_id = p_dealer_id and i.status = 'available'
  ), priced as (
    select b.*,
           case when b.b_price is null or b.b_price <= 0 then null
                when b.b_currency = 'USD' then b.b_price
                when b.b_currency = 'ARS' then round(b.b_price / nullif(v_blue, 0), 2)
           end as b_price_usd,
           (select to_jsonb(s) from public.dealer_alert_state s where s.item_id = b.b_item_id) as b_state
      from base b
  )
  select p.b_item_id, p.b_listing_id, p.b_make, p.b_model, p.b_trim, p.b_year, p.b_km,
         p.b_price, p.b_currency, p.b_price_usd,
         public.dealer_market_ref(p.b_make, p.b_model, p.b_year, p.b_price_usd, p.b_listing_id),
         public.dealer_model_days_to_sell(p.b_make, p.b_model, p.b_year),
         ((now() at time zone 'America/Argentina/Buenos_Aires')::date - p.b_since)::integer,
         case when v_d.approved_at is not null then
           public.dealer_demand(p.b_make, p.b_model, p.b_year, p.b_price, p.b_currency, p.b_km,
                                v_d.lat, v_d.lon, v_members, p.b_source) -> 'zone'
         end,
         (select jsonb_build_object('listing_id', o.id, 'price_usd', o.price_usd, 'year', o.year,
                                    'mileage_km', o.mileage_km, 'source', o.source, 'source_name', s.name,
                                    'distance_km', round(public.haversine_km(v_d.lat, v_d.lon, o.lat, o.lon)::numeric))
            from public.listings o
            left join public.sources s on s.id = o.source
           where p.b_price_usd > 0
             and lower(o.make) = lower(p.b_make) and lower(o.model) = lower(p.b_model)
             and o.year between p.b_year - 1 and p.b_year + 1
             and o.status = 'active'
             and o.last_seen_at >= now() - interval '30 days'
             and o.price_usd > 0 and not o.price_partial
             and o.source <> 'directo'
             and o.id is distinct from p.b_listing_id
             and o.dealer_id is distinct from p_dealer_id
             and not (o.attributes ? '_not_vehicle')
             and o.first_seen_at > coalesce((p.b_state ->> 'cheaper_since')::timestamptz, now())
             and o.price_usd <= p.b_price_usd * (1 - greatest(coalesce(p_cheaper_pct, 8), 1) / 100)
             and (o.mileage_km is null or p.b_km is null or o.mileage_km <= p.b_km * 1.3 + 5000)
             and o.lat is not null and o.lon is not null
             and public.haversine_km(v_d.lat, v_d.lon, o.lat, o.lon) <= coalesce(p_radius_km, 30)
           order by o.price_usd, o.id
           limit 1),
         p.b_state
    from priced p
   order by p.b_created_at, p.b_item_id;
end $$;

revoke all on function public.dealer_set_alerts(boolean) from public, anon;
grant execute on function public.dealer_set_alerts(boolean) to authenticated, service_role;
revoke all on function public.dealer_alert_scan(bigint, numeric, numeric) from public, anon, authenticated;
grant execute on function public.dealer_alert_scan(bigint, numeric, numeric) to service_role;

comment on function public.dealer_alert_scan(bigint, numeric, numeric) is
  'Worker only: per available car of a dealer, the market reference, model days to sell, days in stock, raw demand '
  'in the dealer''s zone (approved dealers only; never shown under demand_min_count people), the cheapest new '
  'look-alike nearby, and dealer_alert_state.';

-- ---------------------------------------------------------------------------
-- 3. Stock from a photo or a PDF of the list
-- ---------------------------------------------------------------------------

create table public.dealer_stock_reads (
  id         bigint generated always as identity primary key,
  dealer_id  bigint not null references public.dealers (id) on delete cascade,
  job_id     bigint references public.llm_jobs (id) on delete set null,
  media_type text not null check (media_type in ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')),
  filename   text check (filename is null or char_length(filename) <= 200),
  bytes      integer not null check (bytes between 1 and 4194304),
  data       bytea,                    -- the file; the worker sets it null as soon as it reads it
  created_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  read_at    timestamptz
);
create index dealer_stock_reads_dealer_idx on public.dealer_stock_reads (dealer_id, created_at desc);
create index dealer_stock_reads_job_idx on public.dealer_stock_reads (job_id) where job_id is not null;
create index dealer_stock_reads_created_by_idx on public.dealer_stock_reads (created_by) where created_by is not null;
create index dealer_stock_reads_unread_idx on public.dealer_stock_reads (created_at) where data is not null;

alter table public.dealer_stock_reads enable row level security;
revoke all on public.dealer_stock_reads from public, anon, authenticated;
grant all on public.dealer_stock_reads to service_role;

alter table public.llm_jobs drop constraint llm_jobs_kind_check;
alter table public.llm_jobs add constraint llm_jobs_kind_check
  check (kind in ('parse_search', 'extract_listing_facts', 'polish_questions', 'model_guide', 'dealer_stock_read'));

alter table public.llm_jobs add constraint llm_jobs_dealer_stock_read_input check (
  kind <> 'dealer_stock_read'
  or coalesce(jsonb_typeof(input -> 'read_id') = 'number' and jsonb_typeof(input -> 'dealer_id') = 'number', false)
);

-- A user cannot enqueue a guide nor a stock read by inserting directly: only
-- admin_request_model_guide and dealer_request_stock_read do (caps).
drop policy "llm_jobs: enqueue own" on public.llm_jobs;
create policy "llm_jobs: enqueue own" on public.llm_jobs
  for insert to authenticated
  with check (user_id = (select auth.uid()) and status = 'queued'
              and kind not in ('model_guide', 'dealer_stock_read'));

-- «Subí una foto o un PDF de tu lista»: checks the switch, the membership, the
-- type and size, and the dealer's daily cap (Argentina's day, every read
-- counts, under the dealer's row lock so two requests can't both take the
-- last one); stores the file for the worker and queues the job. Returns the
-- llm_jobs id the web waits on (RLS: the user reads their own job).
create function public.dealer_request_stock_read(p_data text, p_media_type text, p_filename text default null)
returns bigint
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_uid    uuid := (select auth.uid());
  v_prog   jsonb := public.dealer_program();
  v_bytes  bytea;
  v_today  timestamptz := date_trunc('day', now() at time zone 'America/Argentina/Buenos_Aires')
                            at time zone 'America/Argentina/Buenos_Aires';
  v_read   bigint;
  v_job    bigint;
begin
  if not (v_prog ->> 'photo_import_enabled')::boolean then
    raise exception 'photo_import_off' using errcode = 'P0001';
  end if;
  if p_media_type is null or p_media_type not in ('image/jpeg', 'image/png', 'image/webp', 'application/pdf') then
    raise exception 'invalid_file:type' using errcode = 'P0001';
  end if;
  if p_data is null or length(p_data) = 0 then
    raise exception 'invalid_file:data' using errcode = 'P0001';
  end if;
  if length(p_data) > 5600000 then                          -- 4 MB of base64, with room for line breaks
    raise exception 'file_too_big' using errcode = 'P0001';
  end if;
  begin
    v_bytes := decode(p_data, 'base64');
  exception when others then
    raise exception 'invalid_file:data' using errcode = 'P0001';
  end;
  if length(v_bytes) = 0 then
    raise exception 'invalid_file:data' using errcode = 'P0001';
  end if;
  if length(v_bytes) > 4194304 then
    raise exception 'file_too_big' using errcode = 'P0001';
  end if;

  perform 1 from public.dealers d where d.id = v_dealer for update;
  if (select count(*) from public.dealer_stock_reads r
       where r.dealer_id = v_dealer and r.created_at >= v_today)
     >= (v_prog ->> 'photo_import_daily_limit')::integer then
    raise exception 'photo_import_limit' using errcode = 'P0001';
  end if;

  insert into public.dealer_stock_reads (dealer_id, media_type, filename, bytes, data, created_by)
  values (v_dealer, p_media_type, left(nullif(btrim(p_filename), ''), 200), length(v_bytes), v_bytes, v_uid)
  returning id into v_read;
  -- The hourly llm_jobs cap (enforce_llm_rate_limit) runs here too: llm_rate_limited.
  insert into public.llm_jobs (user_id, kind, input)
  values (v_uid, 'dealer_stock_read', jsonb_build_object('read_id', v_read, 'dealer_id', v_dealer))
  returning id into v_job;
  update public.dealer_stock_reads set job_id = v_job where id = v_read;
  return v_job;
end $$;

revoke all on function public.dealer_request_stock_read(text, text, text) from public, anon;
grant execute on function public.dealer_request_stock_read(text, text, text) to authenticated, service_role;

-- Imports from a photo or a PDF are recorded as such.
alter table public.dealer_imports drop constraint dealer_imports_kind_check;
alter table public.dealer_imports add constraint dealer_imports_kind_check
  check (kind in ('csv', 'xlsx', 'photo', 'pdf'));

-- The body of 20261228120000_dealer_program.sql, with the two new kinds.
create or replace function public.dealer_import_items(p_rows jsonb, p_filename text, p_kind text) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer  bigint := public.dealer_require_member();
  v_uid     uuid := (select auth.uid());
  v_row     jsonb;
  v_line    bigint;
  v_problem text;
  v_import  bigint;
  v_count   integer;
begin
  if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
    raise exception 'invalid_item:rows' using errcode = 'P0001';
  end if;
  v_count := jsonb_array_length(p_rows);
  if v_count > 500 then
    raise exception 'too_many_rows' using errcode = 'P0001';
  end if;
  if p_kind is null or p_kind not in ('csv', 'xlsx', 'photo', 'pdf') then
    raise exception 'invalid_item:kind' using errcode = 'P0001';
  end if;
  for v_row, v_line in select r.value, r.ord from jsonb_array_elements(p_rows) with ordinality r (value, ord) loop
    v_problem := public.dealer_item_problem(v_row);
    if v_problem is not null then
      raise exception 'invalid_item:%:%', v_line, v_problem using errcode = 'P0001';
    end if;
  end loop;

  insert into public.dealer_imports (dealer_id, filename, kind, rows_total, rows_imported, created_by)
  values (v_dealer, left(nullif(btrim(p_filename), ''), 200), p_kind, v_count, v_count, v_uid)
  returning id into v_import;

  insert into public.dealer_stock_items (dealer_id, origin, import_id, make, model, trim, year, mileage_km, price,
                                         currency, transmission, fuel, color, body_type, title, description, images,
                                         in_stock_since, confirmed_at, sync_state, created_by)
  select v_dealer, 'sheet', v_import, f.make, f.model, f.trim, f.year, f.mileage_km, f.price, f.currency,
         f.transmission, f.fuel, f.color, f.body_type, f.title, f.description, f.images, f.in_stock_since,
         now(), 'pending', v_uid
    from jsonb_array_elements(p_rows) with ordinality r (value, ord)
   cross join lateral public.dealer_item_fields(
           (select coalesce(jsonb_object_agg(e.key, e.value), '{}'::jsonb) from jsonb_each(r.value) e)) f
   order by r.ord;

  return jsonb_build_object('import_id', v_import, 'imported', v_count);
end $$;

notify pgrst, 'reload schema';
