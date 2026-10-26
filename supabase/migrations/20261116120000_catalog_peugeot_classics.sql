-- Peugeot classics: the catalog had Peugeot from the 206 on, but people still
-- search (and sell) the older ones: a first search for "Peugeot 106 swap 1.6"
-- (llm_jobs #61, 2026-10-26, catalog_misses 'peugeot 106') ended without a
-- model, and its owner left without saving anything.
--
-- Only rows are added; no existing make, model or trim changes. These models
-- were sold here before the catalog's usual 2003 cut and their exact years
-- aren't fixed, so year_from / year_to stay null: the form offers every year
-- since 1990 and the assisted mode adds no "se fabricó" warning. No trims
-- (the version is free text), as with the other models added without them.
--
-- Same rows as seed.sql (which runs after migrations on `supabase db reset`).

with models (make, model, aliases, year_from, year_to, transmissions, fuels, trims) as (values
  ('Peugeot', '106', '{peugeot 106}', null, null, '{manual}', '{nafta}', '{}'),
  ('Peugeot', '205', '{peugeot 205}', null, null, '{manual}', '{nafta,diesel}', '{}'),
  ('Peugeot', '404', '{peugeot 404}', null, null, '{manual}', '{nafta,diesel}', '{}'),
  ('Peugeot', '405', '{peugeot 405}', null, null, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('Peugeot', '504', '{peugeot 504}', null, null, '{manual}', '{nafta,diesel}', '{}')
)
insert into public.vehicle_catalog (make, model, trim, aliases, year_from, year_to, transmissions, fuels)
select make, model, null, aliases::text[], year_from::int, year_to::int, transmissions::text[], fuels::text[]
  from models
on conflict on constraint vehicle_catalog_unique do nothing;

-- Body types (docs/CARROCERIA.md), every row of the model.
update public.vehicle_catalog c set body_types = v.body_types::text[]
  from (values
    ('Peugeot', '106', '{hatchback}'),
    ('Peugeot', '205', '{hatchback}'),
    ('Peugeot', '404', '{sedan,pickup}'),
    ('Peugeot', '405', '{sedan,rural}'),
    ('Peugeot', '504', '{sedan,pickup,rural}')
  ) as v (make, model, body_types)
 where lower(c.make) = lower(v.make) and lower(c.model) = lower(v.model);
