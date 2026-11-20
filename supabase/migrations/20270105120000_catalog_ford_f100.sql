-- Ford F-100: Juan asked on 20/11/2026 for the F-100 in all its versions and
-- years. It was built in Argentina (General Pacheco) from 1959 to about
-- 1993–1996, then imported from Brazil (F-100 Duty / Super Duty) until 2011, so
-- it should already have been part of the "since 2003" catalog
-- (20261102120000_catalog_all_models) and was missed.
--
-- Only rows are added; no existing make, model or trim changes. Years are the
-- whole Argentine run (1959–2011): the search form now starts a model's year
-- list at its year_from, down to 1950, instead of clamping it at 1990.
-- Aliases have the same shape as the F-150's ('{f150,f 150,lobo}').
--
-- Trims: Standard, XL, XLT, Duty, Super Duty.
-- - "Standard" is spelled as the catalog's other base versions (Foton Tunland,
--   GWM Wingle). normalization/vehicle.py resolve_trim matches trim names as
--   whole words with no aliases, so a title saying only "Std" or "STD" gets no
--   trim (the model still resolves); adding "STD" as a second trim would split
--   one version in two in the form.
-- - "Duty" and "Super Duty": resolve_trim takes the longest name found, so
--   "F-100 Super Duty" gets Super Duty and "F-100 Duty" gets Duty.
-- - Left out: "Ranger" (some 70s/80s F-100s carried it, but the title matcher
--   would mix it up with the Ranger model), and V8, 4x4 and Diesel, which are
--   engine, drivetrain and fuel, not versions.
--
-- Trim rows copy the model row's body_types.
-- Same rows as seed.sql (which runs after migrations on `supabase db reset`).

with models (make, model, aliases, year_from, year_to, transmissions, fuels) as (values
  ('Ford', 'F-100', '{f100,f 100}', 1959, 2011, '{manual}', '{nafta,diesel,gnc}')
)
insert into public.vehicle_catalog (make, model, trim, aliases, year_from, year_to, transmissions, fuels)
select make, model, null, aliases::text[], year_from, year_to, transmissions::text[], fuels::text[]
  from models
on conflict on constraint vehicle_catalog_unique do nothing;

-- Body types (docs/CARROCERIA.md) of the model row.
update public.vehicle_catalog c set body_types = v.body_types::text[]
  from (values
    ('Ford', 'F-100', '{pickup}')
  ) as v (make, model, body_types)
 where lower(c.make) = lower(v.make) and lower(c.model) = lower(v.model);

insert into public.vehicle_catalog (make, model, trim, body_types)
select m.make, m.model, v.trim, m.body_types
  from (values
    ('Ford', 'F-100', 'Standard'),
    ('Ford', 'F-100', 'XL'),
    ('Ford', 'F-100', 'XLT'),
    ('Ford', 'F-100', 'Duty'),
    ('Ford', 'F-100', 'Super Duty')
  ) as v (make, model, trim)
  join public.vehicle_catalog m on m.make = v.make and m.model = v.model and m.trim is null
on conflict on constraint vehicle_catalog_unique do nothing;
