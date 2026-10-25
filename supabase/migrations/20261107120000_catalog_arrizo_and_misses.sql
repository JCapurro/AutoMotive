-- Chery Arrizo 5 and Arrizo 8, missing from the catalog: a new user asked the
-- assisted mode for «CHERY ARRIZO 8», got "No encontramos «Chery Arrizo 8» en
-- el catálogo" with the model empty and left without saving (25/10/2026).
--
-- Researched 25/10/2026 for the Argentine market:
-- - Arrizo 5: sedan sold since the end of 2017 (2018 models) in Confort
--   (manual) and Luxury (manual and CVT), 1.5 nafta (Autocosmos, 16valvulas,
--   Mercado Libre listings 2018–2022). No confirmed end of sale: year_to null.
-- - Arrizo 8: plug-in hybrid sedan imported by Grupo Corven since January
--   2026, Comfort; Luxury added in October 2026 (Autoweb). Comfort is the
--   name Corven uses for it, not the Confort of the older Chery.
--
-- Also catalog_misses: the models people ask for that the catalog doesn't
-- have, so the next gap shows up in /admin/catalog-misses instead of in an
-- abandoned search. The worker records them (pipeline/llm_jobs.py).
--
-- Same rows as seed.sql (which runs after migrations on `supabase db reset`).

with models (make, model, aliases, year_from, year_to, transmissions, fuels, trims) as (values
  ('Chery', 'Arrizo 5', '{arrizo5}', 2018, null::integer, '{manual,automatic}', '{nafta}', '{}'),
  ('Chery', 'Arrizo 8', '{arrizo8}', 2026, null, '{automatic}', '{hibrido}', '{}')
)
insert into public.vehicle_catalog (make, model, trim, aliases, year_from, year_to, transmissions, fuels)
select make, model, null, aliases::text[], year_from, year_to, transmissions::text[], fuels::text[]
  from models
on conflict on constraint vehicle_catalog_unique do nothing;

-- Body types (docs/CARROCERIA.md), every row of the model.
update public.vehicle_catalog c set body_types = v.body_types::text[]
  from (values
    ('Chery', 'Arrizo 5', '{sedan}'),
    ('Chery', 'Arrizo 8', '{sedan}')
  ) as v (make, model, body_types)
 where lower(c.make) = lower(v.make) and lower(c.model) = lower(v.model);

-- Trims, with the model row's body_types (as 20261103120000_catalog_all_trims).
insert into public.vehicle_catalog (make, model, trim, body_types)
select m.make, m.model, v.trim, m.body_types
  from (values
    ('Chery', 'Arrizo 5', 'Confort'),
    ('Chery', 'Arrizo 5', 'Luxury'),
    ('Chery', 'Arrizo 8', 'Comfort'),
    ('Chery', 'Arrizo 8', 'Luxury')
  ) as v (make, model, trim)
  join public.vehicle_catalog m on m.make = v.make and m.model = v.model and m.trim is null
on conflict on constraint vehicle_catalog_unique do nothing;

-- ---------------------------------------------------------------------------
-- catalog_misses
-- ---------------------------------------------------------------------------

-- One row per thing asked for, by its normalized text ("chery arrizo 8"):
-- how many times, first and last. `make` is the catalog make when the make
-- was recognized (null for a make the catalog doesn't have either).
create table public.catalog_misses (
  said           text primary key check (length(said) between 1 and 120),
  make           text,
  count          integer not null default 1 check (count > 0),
  first_seen_at  timestamptz not null default now(),
  last_seen_at   timestamptz not null default now(),
  last_llm_job_id bigint references public.llm_jobs(id) on delete set null
);
create index catalog_misses_count_idx on public.catalog_misses (count desc, last_seen_at desc);
comment on table public.catalog_misses is
  'Makes and models asked for in the assisted mode (parse_search) that vehicle_catalog does not have, '
  'counted by normalized text. Written by the worker; read in /admin/catalog-misses.';

alter table public.catalog_misses enable row level security;
revoke all on public.catalog_misses from public, anon, authenticated, service_role;
grant select, insert, update, delete on public.catalog_misses to service_role;
