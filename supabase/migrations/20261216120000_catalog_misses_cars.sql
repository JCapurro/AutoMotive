-- Cars asked for in the assisted mode that the catalog didn't have
-- (/admin/catalog-misses, 2026-11-14): Fiat 147, Corvette, Falcon, Escort,
-- Volvo V60, Chevy, Audi S4 and Nissan D21. Left out on purpose: the two
-- motorcycles (Honda Wave 110, Voge 300 Rally) and the two texts with no
-- clear make ("150 xtec", "glh").
--
-- Only rows are added. The classics have no fixed years (year_from / year_to
-- null: the form offers every year since 1990, no "se fabricó" warning) and no
-- trims ("Ghia", "Corvette C3" stay free text / alias), as with the Peugeot
-- classics. Same rows as seed.sql.

with models (make, model, aliases, year_from, year_to, transmissions, fuels, trims) as (values
  ('Fiat', '147', '{fiat 147}', null::integer, null::integer, '{manual}', '{nafta}', '{}'),
  ('Chevrolet', 'Corvette', '{chevrolet corvette,corvette c3}', null, null, '{manual,automatic}', '{nafta}', '{}'),
  ('Chevrolet', 'Chevy', '{chevrolet chevy}', null, null, '{manual}', '{nafta}', '{}'),
  ('Ford', 'Falcon', '{ford falcon}', null, null, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('Ford', 'Escort', '{ford escort}', null, null, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('Volvo', 'V60', '{volvo v60}', 2011, null, '{automatic}', '{nafta,diesel,hibrido}', '{}'),
  ('Audi', 'S4', '{audi s4}', null, null, '{manual,automatic}', '{nafta}', '{}'),
  ('Nissan', 'D21', '{nissan d21}', null, null, '{manual}', '{nafta,diesel}', '{}')
)
insert into public.vehicle_catalog (make, model, trim, aliases, year_from, year_to, transmissions, fuels)
select make, model, null, aliases::text[], year_from, year_to, transmissions::text[], fuels::text[]
  from models
on conflict on constraint vehicle_catalog_unique do nothing;

-- Body types (docs/CARROCERIA.md), every row of the model.
update public.vehicle_catalog c set body_types = v.body_types::text[]
  from (values
    ('Fiat', '147', '{hatchback}'),
    ('Chevrolet', 'Corvette', '{coupe,convertible}'),
    ('Chevrolet', 'Chevy', '{sedan,pickup}'),
    ('Ford', 'Falcon', '{sedan,rural}'),
    ('Ford', 'Escort', '{hatchback,sedan,rural}'),
    ('Volvo', 'V60', '{rural}'),
    ('Audi', 'S4', '{sedan}'),
    ('Nissan', 'D21', '{pickup}')
  ) as v (make, model, body_types)
 where lower(c.make) = lower(v.make) and lower(c.model) = lower(v.model);
