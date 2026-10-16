-- Carrocería (docs/CARROCERIA.md): vehicle_catalog.body_types for every model
-- of the catalog. The column comes in 20261030120000_body_type.sql.
--
-- body_types are the bodies a listing resolved to that model can have, most
-- common first. One value means certain: normalization/body_type.py uses it
-- when nothing else says otherwise, and lets it overrule a source's label
-- (Mercado Libre calls some Spin "SUV"). Two or more only bound the choice:
-- the source's label, the doors or the title decide, and the web's selector
-- within a model offers exactly those. '{}' = unknown.
--
-- From Mercado Libre's body type facet per model (15/10/2026): a body counts
-- when it is real for the model and has 3 % or more of the model's listings;
-- "Sedán" on a model with no sedan (Argentine "sedán 5 puertas") and
-- "Hatchback" or "Rural" on a van's passenger version are noise. Submodels
-- the catalog resolves to their parent and the title rules catch by name
-- (Duster Oroch, Gol Country, Golf Variant, i30 CW) don't add their body to
-- the parent unless its facet shows it (Palio: an Adventure is a Weekend that
-- rarely says so). Ka keeps sedan although ML lists the Ka+ apart: it shares
-- the Ka's trims and is often titled "Ka S Plus 4p". A year range is not
-- modelled: C3 Aircross and 3008 changed body between generations and keep
-- both.
--
-- Every row of the model, trims included. Same list as seed.sql (which runs
-- after migrations on `supabase db reset`).
update public.vehicle_catalog c set body_types = v.body_types::text[]
  from (values
    ('Volkswagen', 'Gol', '{hatchback}'), ('Volkswagen', 'Gol Trend', '{hatchback}'),
    ('Volkswagen', 'Suran', '{monovolumen}'), ('Volkswagen', 'Fox', '{hatchback}'),
    ('Volkswagen', 'Up', '{hatchback}'), ('Volkswagen', 'Polo', '{hatchback,sedan}'),
    ('Volkswagen', 'Virtus', '{sedan}'), ('Volkswagen', 'Vento', '{sedan}'),
    ('Volkswagen', 'Bora', '{sedan}'), ('Volkswagen', 'Golf', '{hatchback}'),
    ('Volkswagen', 'Saveiro', '{pickup}'), ('Volkswagen', 'Amarok', '{pickup}'),
    ('Volkswagen', 'T-Cross', '{suv}'), ('Volkswagen', 'Taos', '{suv}'), ('Volkswagen', 'Nivus', '{suv}'),
    ('Toyota', 'Corolla', '{sedan}'), ('Toyota', 'Corolla Cross', '{suv}'),
    ('Toyota', 'Etios', '{hatchback,sedan}'), ('Toyota', 'Yaris', '{hatchback,sedan}'),
    ('Toyota', 'Hilux', '{pickup}'), ('Toyota', 'SW4', '{suv}'),
    ('Ford', 'Fiesta', '{hatchback,sedan}'), ('Ford', 'Focus', '{sedan,hatchback}'),
    ('Ford', 'Ka', '{hatchback,sedan}'), ('Ford', 'EcoSport', '{suv}'), ('Ford', 'Ranger', '{pickup}'),
    ('Ford', 'Territory', '{suv}'), ('Ford', 'Maverick', '{pickup}'),
    ('Chevrolet', 'Onix', '{hatchback}'), ('Chevrolet', 'Onix Plus', '{sedan}'),
    ('Chevrolet', 'Prisma', '{sedan}'), ('Chevrolet', 'Cruze', '{sedan,hatchback}'),
    ('Chevrolet', 'Tracker', '{suv}'), ('Chevrolet', 'S10', '{pickup}'),
    ('Chevrolet', 'Corsa', '{hatchback,sedan,pickup,rural,utilitario}'),
    ('Chevrolet', 'Classic', '{sedan}'), ('Chevrolet', 'Agile', '{hatchback}'),
    ('Chevrolet', 'Spin', '{monovolumen}'),
    ('Renault', 'Sandero', '{hatchback}'), ('Renault', 'Stepway', '{hatchback}'),
    ('Renault', 'Logan', '{sedan}'), ('Renault', 'Clio', '{hatchback,sedan}'),
    ('Renault', 'Kangoo', '{utilitario,monovolumen}'), ('Renault', 'Duster', '{suv}'),
    ('Renault', 'Kwid', '{hatchback}'), ('Renault', 'Captur', '{suv}'),
    ('Renault', 'Fluence', '{sedan}'), ('Renault', 'Alaskan', '{pickup}'),
    ('Fiat', 'Palio', '{hatchback,rural}'), ('Fiat', 'Siena', '{sedan}'), ('Fiat', 'Cronos', '{sedan}'),
    ('Fiat', 'Argo', '{hatchback}'), ('Fiat', 'Mobi', '{hatchback}'),
    ('Fiat', 'Uno', '{hatchback,utilitario}'), ('Fiat', 'Punto', '{hatchback}'),
    ('Fiat', 'Toro', '{pickup}'), ('Fiat', 'Strada', '{pickup}'), ('Fiat', 'Pulse', '{suv}'),
    ('Peugeot', '208', '{hatchback}'), ('Peugeot', '207', '{hatchback,sedan}'),
    ('Peugeot', '206', '{hatchback,rural}'), ('Peugeot', '2008', '{suv}'),
    ('Peugeot', '308', '{hatchback}'), ('Peugeot', '408', '{sedan}'),
    ('Peugeot', '3008', '{monovolumen,suv}'), ('Peugeot', 'Partner', '{utilitario,monovolumen}'),
    ('Citroën', 'C3', '{hatchback}'), ('Citroën', 'C3 Aircross', '{hatchback,suv}'),
    ('Citroën', 'C4', '{hatchback,sedan}'), ('Citroën', 'C4 Lounge', '{sedan}'),
    ('Citroën', 'C4 Cactus', '{suv}'), ('Citroën', 'Berlingo', '{utilitario,monovolumen}'),
    ('Honda', 'Civic', '{sedan,hatchback,coupe}'), ('Honda', 'Fit', '{hatchback}'),
    ('Honda', 'City', '{sedan}'), ('Honda', 'HR-V', '{suv}'), ('Honda', 'CR-V', '{suv}'),
    ('Honda', 'WR-V', '{suv}'),
    ('Nissan', 'March', '{hatchback}'), ('Nissan', 'Versa', '{sedan}'), ('Nissan', 'Sentra', '{sedan}'),
    ('Nissan', 'Note', '{hatchback}'), ('Nissan', 'Tiida', '{hatchback,sedan}'),
    ('Nissan', 'Kicks', '{suv}'), ('Nissan', 'Frontier', '{pickup}'),
    ('Jeep', 'Renegade', '{suv}'), ('Jeep', 'Compass', '{suv}'), ('Jeep', 'Commander', '{suv}'),
    ('Hyundai', 'HB20', '{hatchback,sedan}'), ('Hyundai', 'Creta', '{suv}'),
    ('Hyundai', 'Tucson', '{suv}'), ('Hyundai', 'i30', '{hatchback}'), ('Hyundai', 'Santa Fe', '{suv}'),
    ('Kia', 'Picanto', '{hatchback}'), ('Kia', 'Rio', '{hatchback,sedan}'),
    ('Kia', 'Cerato', '{sedan,hatchback}'), ('Kia', 'Soul', '{suv}'), ('Kia', 'Sportage', '{suv}'),
    ('Kia', 'Seltos', '{suv}'),
    ('Audi', 'A1', '{hatchback}'), ('Audi', 'A3', '{sedan,hatchback}'), ('Audi', 'A4', '{sedan}'),
    ('Audi', 'Q2', '{suv}'), ('Audi', 'Q3', '{suv}'), ('Audi', 'Q5', '{suv}'),
    ('BMW', 'Serie 1', '{hatchback,coupe}'), ('BMW', 'Serie 3', '{sedan,coupe}'),
    ('BMW', 'X1', '{suv}'), ('BMW', 'X3', '{suv}'),
    ('Mercedes-Benz', 'Clase A', '{hatchback,sedan}'), ('Mercedes-Benz', 'Clase C', '{sedan,coupe}'),
    ('Mercedes-Benz', 'GLA', '{suv}'), ('Mercedes-Benz', 'Sprinter', '{utilitario}'),
    ('Mini', 'Cooper', '{hatchback,convertible}'), ('Mini', 'Countryman', '{suv}'),
    ('Subaru', 'Impreza', '{sedan,hatchback}'), ('Subaru', 'XV', '{suv}'),
    ('Subaru', 'Forester', '{suv}'), ('Subaru', 'Outback', '{suv,rural}'),
    ('Mitsubishi', 'Lancer', '{sedan}'), ('Mitsubishi', 'ASX', '{suv}'),
    ('Mitsubishi', 'Outlander', '{suv}'), ('Mitsubishi', 'L200', '{pickup}'),
    ('Suzuki', 'Swift', '{hatchback}'), ('Suzuki', 'Fun', '{hatchback}'), ('Suzuki', 'Vitara', '{suv}'),
    ('Suzuki', 'Grand Vitara', '{suv}'), ('Suzuki', 'Jimny', '{suv}')
  ) as v (make, model, body_types)
 where lower(c.make) = lower(v.make) and lower(c.model) = lower(v.model);
