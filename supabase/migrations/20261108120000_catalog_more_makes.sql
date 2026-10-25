-- More makes: the search form and the assisted mode listed 47 makes, and
-- several that are listed and searched in Argentina were missing (Mazda,
-- Cupra, Jaguar, Jaecoo...). A listing or a search for them
-- kept the source's spelling unresolved, or ended in catalog_misses.
--
-- Only rows are added; no existing make, model or trim changes. Years are
-- the model's Argentine sale years (clipped at 2003, null = still sold),
-- no trims yet (the form takes the version as free text).
--
-- Left out on purpose: Opel and Skoda (no regular sale here since 2003 and
-- "opel"/"skoda" appear in titles as parts), Hummer and Buick (grey import
-- only).
--
-- Same rows as seed.sql (which runs after migrations on `supabase db reset`).

with models (make, model, aliases, year_from, year_to, transmissions, fuels, trims) as (values
  ('Mazda', 'Mazda2', '{mazda 2}', 2008, 2014, '{manual,automatic}', '{nafta}', '{}'),
  ('Mazda', 'Mazda3', '{mazda 3}', 2004, 2019, '{manual,automatic}', '{nafta}', '{}'),
  ('Mazda', 'Mazda6', '{mazda 6}', 2004, 2013, '{manual,automatic}', '{nafta}', '{}'),
  ('Mazda', 'CX-5', '{cx5,cx 5}', 2013, null, '{automatic}', '{nafta}', '{}'),
  ('Mazda', 'CX-3', '{cx3,cx 3}', 2017, 2021, '{automatic}', '{nafta}', '{}'),
  ('Mazda', 'CX-9', '{cx9,cx 9}', 2008, 2023, '{automatic}', '{nafta}', '{}'),
  ('Mazda', 'BT-50', '{bt50,bt 50}', 2008, 2018, '{manual,automatic}', '{diesel}', '{}'),
  ('Cupra', 'Formentor', '{}', 2022, null, '{automatic}', '{nafta,hibrido}', '{}'),
  ('Cupra', 'Born', '{}', 2024, null, '{automatic}', '{electrico}', '{}'),
  ('Cupra', 'Leon', '{león}', 2022, null, '{automatic}', '{nafta}', '{}'),
  ('Jaguar', 'XF', '{}', 2009, 2024, '{automatic}', '{nafta,diesel}', '{}'),
  ('Jaguar', 'XE', '{}', 2016, 2024, '{automatic}', '{nafta,diesel}', '{}'),
  ('Jaguar', 'F-Pace', '{fpace,f pace}', 2017, null, '{automatic}', '{nafta,diesel}', '{}'),
  ('Jaguar', 'E-Pace', '{epace,e pace}', 2018, null, '{automatic}', '{nafta,diesel}', '{}'),
  ('Jaguar', 'F-Type', '{ftype,f type}', 2014, null, '{automatic}', '{nafta}', '{}'),
  ('Jaecoo', 'J7', '{jaecoo7}', 2025, null, '{automatic}', '{nafta,hibrido}', '{}'),
  ('Maserati', 'Ghibli', '{}', 2014, 2023, '{automatic}', '{nafta,diesel}', '{}'),
  ('Maserati', 'Levante', '{}', 2017, null, '{automatic}', '{nafta,diesel}', '{}'),
  ('Maserati', 'Quattroporte', '{}', 2004, 2023, '{automatic}', '{nafta,diesel}', '{}'),
  ('Infiniti', 'Q50', '{}', 2014, 2019, '{automatic}', '{nafta}', '{}'),
  ('Infiniti', 'QX50', '{}', 2014, 2019, '{automatic}', '{nafta}', '{}'),
  ('Infiniti', 'QX60', '{}', 2014, 2019, '{automatic}', '{nafta}', '{}'),
  ('Isuzu', 'D-Max', '{dmax,d max}', 2004, 2012, '{manual,automatic}', '{diesel}', '{}'),
  ('Lincoln', 'Navigator', '{}', 2003, null, '{automatic}', '{nafta}', '{}'),
  ('Lincoln', 'MKZ', '{}', 2013, 2020, '{automatic}', '{nafta,hibrido}', '{}'),
  ('Cadillac', 'Escalade', '{}', 2003, null, '{automatic}', '{nafta}', '{}'),
  ('Cadillac', 'CTS', '{}', 2005, 2018, '{automatic}', '{nafta}', '{}'),
  ('Dongfeng', 'Rich 6', '{rich6}', 2022, null, '{manual,automatic}', '{diesel}', '{}'),
  ('Dongfeng', 'Shine', '{}', 2022, null, '{manual,automatic}', '{nafta}', '{}'),
  ('BAIC', 'X35', '{}', 2018, 2022, '{manual,automatic}', '{nafta}', '{}'),
  ('BAIC', 'X55', '{}', 2019, 2024, '{manual,automatic}', '{nafta}', '{}'),
  ('Leapmotor', 'T03', '{}', 2024, null, '{automatic}', '{electrico}', '{}'),
  ('Leapmotor', 'C10', '{}', 2025, null, '{automatic}', '{electrico,hibrido}', '{}'),
  ('Zeekr', '001', '{}', 2025, null, '{automatic}', '{electrico}', '{}'),
  ('Zeekr', 'X', '{}', 2025, null, '{automatic}', '{electrico}', '{}'),
  ('Mahindra', 'Pik Up', '{pickup,pik-up}', 2010, 2018, '{manual}', '{diesel}', '{}'),
  ('Mahindra', 'XUV500', '{xuv 500}', 2012, 2018, '{manual,automatic}', '{diesel}', '{}')
)
insert into public.vehicle_catalog (make, model, trim, aliases, year_from, year_to, transmissions, fuels)
select make, model, null, aliases::text[], year_from, year_to, transmissions::text[], fuels::text[]
  from models
on conflict on constraint vehicle_catalog_unique do nothing;

-- Body types (docs/CARROCERIA.md), every row of the model.
update public.vehicle_catalog c set body_types = v.body_types::text[]
  from (values
    ('Mazda', 'Mazda2', '{hatchback,sedan}'),
    ('Mazda', 'Mazda3', '{sedan,hatchback}'),
    ('Mazda', 'Mazda6', '{sedan,rural}'),
    ('Mazda', 'CX-5', '{suv}'),
    ('Mazda', 'CX-3', '{suv}'),
    ('Mazda', 'CX-9', '{suv}'),
    ('Mazda', 'BT-50', '{pickup}'),
    ('Cupra', 'Formentor', '{suv}'),
    ('Cupra', 'Born', '{hatchback}'),
    ('Cupra', 'Leon', '{hatchback}'),
    ('Jaguar', 'XF', '{sedan}'),
    ('Jaguar', 'XE', '{sedan}'),
    ('Jaguar', 'F-Pace', '{suv}'),
    ('Jaguar', 'E-Pace', '{suv}'),
    ('Jaguar', 'F-Type', '{coupe,convertible}'),
    ('Jaecoo', 'J7', '{suv}'),
    ('Maserati', 'Ghibli', '{sedan}'),
    ('Maserati', 'Levante', '{suv}'),
    ('Maserati', 'Quattroporte', '{sedan}'),
    ('Infiniti', 'Q50', '{sedan}'),
    ('Infiniti', 'QX50', '{suv}'),
    ('Infiniti', 'QX60', '{suv}'),
    ('Isuzu', 'D-Max', '{pickup}'),
    ('Lincoln', 'Navigator', '{suv}'),
    ('Lincoln', 'MKZ', '{sedan}'),
    ('Cadillac', 'Escalade', '{suv}'),
    ('Cadillac', 'CTS', '{sedan}'),
    ('Dongfeng', 'Rich 6', '{pickup}'),
    ('Dongfeng', 'Shine', '{suv}'),
    ('BAIC', 'X35', '{suv}'),
    ('BAIC', 'X55', '{suv}'),
    ('Leapmotor', 'T03', '{hatchback}'),
    ('Leapmotor', 'C10', '{suv}'),
    ('Zeekr', '001', '{rural}'),
    ('Zeekr', 'X', '{suv}'),
    ('Mahindra', 'Pik Up', '{pickup}'),
    ('Mahindra', 'XUV500', '{suv}')
  ) as v (make, model, body_types)
 where lower(c.make) = lower(v.make) and lower(c.model) = lower(v.model);
