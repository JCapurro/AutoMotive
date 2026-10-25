-- Timing drive of the most listed models (docs/DISTRIBUCION.md, which has
-- the source of every value). NOT APPLIED: Juan reviews the table first.
--
-- vehicle_catalog.timing_belt is one value per model (the row with trim
-- null); the catalog has no rows per engine or year. So a model is marked
-- only when every engine it had in Argentina in the years of its catalog
-- row and of its listings drives the cams the same way, confirmed by a data
-- sheet or the specialized press. When it depends on the engine or the year
-- (a Hilux 3.0 1KD has a belt, a 2.8 1GD a chain) it is null: null raises no
-- no_timing_belt red flag and keeps the model out of a «cadenero» search
-- (normalization/drafts.py), which is the safe side of both.
--
-- seed.sql repeats this list after the F2 one, so `supabase db reset` agrees.

update public.vehicle_catalog c set timing_belt = v.belt
  from (values
    -- Chain in every engine sold here in the catalog's years.
    ('Toyota', 'Corolla Cross', false), ('Fiat', 'Cronos', false), ('Fiat', 'Argo', false),
    ('Fiat', 'Pulse', false), ('Renault', 'Kwid', false), ('Renault', 'Kardian', false),
    ('Nissan', 'Kicks', false), ('Nissan', 'Versa', false), ('Nissan', 'Sentra', false),
    ('Ford', 'Territory', false),
    -- Belt (dry or in oil) in every engine sold here.
    ('Volkswagen', 'Polo', true), ('Volkswagen', 'Virtus', true), ('Volkswagen', 'T-Cross', true),
    ('Volkswagen', 'Nivus', true), ('Volkswagen', 'Taos', true), ('Volkswagen', 'Bora', true),
    ('Chevrolet', 'Celta', true), ('Fiat', 'Fiorino', true)
  ) as v (make, model, belt)
 where c.make = v.make and c.model = v.model and c.trim is null;

-- Corrections of the F2 list (20260929120000_f2_intelligence.sql): these
-- depend on the engine, so they go back to unknown.
--   Chain there, but with belt engines in years the catalog row covers:
--   Corolla (7A-FE 1998–2002, 2.0 diesel), Hilux and SW4 (1KD/2KD
--   2005–2015), Civic (D series up to 2005).
--   Belt there, but with chain engines: Focus (Duratec 2.0, EcoBoost),
--   EcoSport and Ka (Zetec Rocam; EcoSport 2.0 Duratec), 208 (1.6 THP,
--   1.0 T200). Dropping their `true` turns off the no_timing_belt flag for
--   them, which today also fires on chain engines.
update public.vehicle_catalog c set timing_belt = null
  from (values
    ('Toyota', 'Corolla'), ('Toyota', 'Hilux'), ('Toyota', 'SW4'), ('Honda', 'Civic'),
    ('Ford', 'Focus'), ('Ford', 'EcoSport'), ('Ford', 'Ka'), ('Peugeot', '208')
  ) as v (make, model)
 where c.make = v.make and c.model = v.model and c.trim is null;
