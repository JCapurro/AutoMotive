-- Reference data for the Automotive MVP. Runs after the migrations on `supabase db reset`.
-- Every insert is idempotent and never overwrites values already tuned in the database.

-- ---------------------------------------------------------------------------
-- sources (sección 5.1). detail_interval_seconds rate-limits fetch_detail() (sección 5.5).
-- ---------------------------------------------------------------------------

insert into public.sources (id, name, enabled, crawl_interval_seconds, priority, detail_interval_seconds) values
  ('mercadolibre', 'MercadoLibre',         true,   600, 10,  8),
  ('kavak',        'Kavak',                true,  1800, 20,  5),
  ('v6',           'V6',                   true,  1800, 30,  5),
  ('facebook',     'Facebook Marketplace', true,  3600, 40, 30),
  ('autocosmos',   'Autocosmos',           true,  1800, 50,  5)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- app_config: business rules (Apéndice A)
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  ('score_weights',                 '{"price": 35, "match": 25, "km": 15, "trim": 10, "recency": 10, "completeness": 5}'),
  ('level_thresholds',              '{"high": 85, "good": 70, "match": 50}'),
  ('comparables',                   '{"min_n": 5, "year_tol": 1, "km_tol_pct": 25, "max_age_days": 30}'),
  ('recommended_max_age_days',      '15'),
  ('price_drop_min_pct',            '3'),
  ('alerts_max_per_user_day',       '10'),
  ('digest_hour',                   '"20:00"'),
  ('watchlist_stale_days',          '30'),
  ('collector_failure_alert_after', '3'),
  ('plan_limits', '{
     "enforced": false,
     "free": {"max_profiles": 1, "max_visible_results": 50, "immediate_alerts": false},
     "pro":  {"max_profiles": 10, "immediate_alerts": true, "crawl_priority": "high"}
   }'),
  ('repost',                        '{"window_days": 60, "price_tol_pct": 10}'),
  ('enrichment',                    '{"batch_per_source": 20, "max_age_days": 30}'),
  ('score_curves', '{
     "price":        {"base": 0.5, "pct_per_unit": 20},
     "match":        {"unknown_penalty": 0.15},
     "km":           {"base": 0.5, "slope": 1.25},
     "trim":         {"preferred": 1, "unknown": 0.5, "other": 0.2, "no_preference": 1},
     "recency":      {"half_life_hours": 24},
     "completeness": {"min_description_chars": 150, "min_images": 3},
     "guards":       {"suspicious_pct": 50, "partial_pct": 65}
   }'),
  ('red_flags',                     '{"much_cheaper_pct": 25, "anticipo_pct": 50, "min_km_per_year": 5000, "min_description_chars": 150}'),
  ('rescore',                       '{"days": 14, "hour": "04:00"}'),
  ('digest_top_n',                  '10')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- vehicle_catalog: most searched models in Argentina.
-- A model-level row (trim null) carries aliases, years, transmissions and fuels;
-- one extra row per known trim. Years are only filled where the range is well known.
-- ---------------------------------------------------------------------------

with models (make, model, aliases, year_from, year_to, transmissions, fuels, trims) as (values
  -- Volkswagen
  ('Volkswagen', 'Gol',        '{gol power}',                          1995, 2014, '{manual}',           '{nafta,gnc}',    '{}'),
  ('Volkswagen', 'Gol Trend',  '{goltrend}',                           2008, 2023, '{manual,automatic}', '{nafta,gnc}',    '{Trendline,Comfortline,Highline,Pack I,Pack II,Pack III}'),
  ('Volkswagen', 'Suran',      '{suran cross}',                        2006, 2019, '{manual}',           '{nafta,gnc}',    '{Trendline,Comfortline,Highline,Track}'),
  ('Volkswagen', 'Fox',        '{crossfox}',                           2004, 2021, '{manual}',           '{nafta}',        '{Trendline,Comfortline,Highline}'),
  ('Volkswagen', 'Up',         '{up!,take up,move up,high up,cross up}', 2014, 2020, '{manual}',         '{nafta}',        '{Take up!,Move up!,High up!,Cross up!}'),
  ('Volkswagen', 'Polo',       '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Trendline,Comfortline,Highline,GTS,Track}'),
  ('Volkswagen', 'Virtus',     '{}',                                   2018, null, '{manual,automatic}', '{nafta}',        '{Trendline,Comfortline,Highline,GTS}'),
  ('Volkswagen', 'Vento',      '{}',                                   2006, null, '{manual,automatic}', '{nafta,diesel}', '{Advance,Luxury,Comfortline,Highline,Sportline,GLI}'),
  ('Volkswagen', 'Bora',       '{}',                                   2000, 2015, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('Volkswagen', 'Golf',       '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{Trendline,Comfortline,Highline,GTI}'),
  ('Volkswagen', 'Saveiro',    '{}',                                   null, null, '{manual}',           '{nafta,gnc}',    '{Trendline,Comfortline,Highline,Cross}'),
  ('Volkswagen', 'Amarok',     '{}',                                   2010, null, '{manual,automatic}', '{diesel}',       '{Trendline,Comfortline,Highline,Extreme,V6}'),
  ('Volkswagen', 'T-Cross',    '{tcross,t cross}',                     2019, null, '{manual,automatic}', '{nafta}',        '{Trendline,Comfortline,Highline,Hero}'),
  ('Volkswagen', 'Taos',       '{}',                                   2021, null, '{automatic}',        '{nafta}',        '{Comfortline,Highline,Hero}'),
  ('Volkswagen', 'Nivus',      '{}',                                   2020, null, '{automatic}',        '{nafta}',        '{Comfortline,Highline,Hero}'),
  -- Toyota
  ('Toyota', 'Corolla',        '{}',                                   null, null, '{manual,automatic}', '{nafta,hibrido}', '{XLI,XEI,SEG,GR-Sport,HEV}'),
  ('Toyota', 'Corolla Cross',  '{corollacross}',                       2021, null, '{automatic}',        '{nafta,hibrido}', '{XLI,XEI,SEG,GR-Sport}'),
  ('Toyota', 'Etios',          '{etios cross}',                        2013, 2023, '{manual,automatic}', '{nafta}',        '{X,XS,XLS}'),
  ('Toyota', 'Yaris',          '{}',                                   2018, null, '{manual,automatic}', '{nafta}',        '{XS,XLS,S}'),
  ('Toyota', 'Hilux',          '{}',                                   null, null, '{manual,automatic}', '{diesel,nafta}', '{DX,SR,SRV,SRX,GR-Sport,Conquest}'),
  ('Toyota', 'SW4',            '{sw 4,hilux sw4}',                     null, null, '{manual,automatic}', '{diesel,nafta}', '{SR,SRV,SRX,Diamond,GR-Sport}'),
  -- Ford
  ('Ford', 'Fiesta',           '{fiesta kinetic,fiesta kinetic design,fiesta max}', null, 2019, '{manual,automatic}', '{nafta,diesel}', '{S,SE,SEL,Titanium,ST}'),
  ('Ford', 'Focus',            '{}',                                   null, 2019, '{manual,automatic}', '{nafta,diesel}', '{S,SE,SE Plus,Titanium,ST}'),
  ('Ford', 'Ka',               '{ka+,ka plus}',                        null, 2021, '{manual}',           '{nafta}',        '{S,SE,SEL,Freestyle}'),
  ('Ford', 'EcoSport',         '{eco sport}',                          2003, 2022, '{manual,automatic}', '{nafta,diesel}', '{S,SE,Titanium,Freestyle,Storm}'),
  ('Ford', 'Ranger',           '{}',                                   null, null, '{manual,automatic}', '{diesel,nafta}', '{XL,XLS,XLT,Limited,Black,Raptor}'),
  ('Ford', 'Territory',        '{}',                                   2020, null, '{automatic}',        '{nafta}',        '{Trend,SEL,Titanium}'),
  ('Ford', 'Maverick',         '{}',                                   2022, null, '{automatic}',        '{nafta,hibrido}', '{XLT,Lariat,Tremor}'),
  -- Chevrolet
  ('Chevrolet', 'Onix',        '{onix joy}',                           2013, null, '{manual,automatic}', '{nafta}',        '{LS,LT,LTZ,Joy,Premier,RS}'),
  ('Chevrolet', 'Onix Plus',   '{onixplus}',                           2020, null, '{manual,automatic}', '{nafta}',        '{LT,LTZ,Premier}'),
  ('Chevrolet', 'Prisma',      '{prisma joy}',                         2013, 2019, '{manual,automatic}', '{nafta}',        '{LS,LT,LTZ,Joy}'),
  ('Chevrolet', 'Cruze',       '{}',                                   2010, null, '{manual,automatic}', '{nafta,diesel}', '{LT,LTZ,Premier,RS}'),
  ('Chevrolet', 'Tracker',     '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LS,LT,LTZ,Premier,RS}'),
  ('Chevrolet', 'S10',         '{s-10,s 10}',                          null, null, '{manual,automatic}', '{diesel}',       '{LS,LT,LTZ,High Country,Z71}'),
  ('Chevrolet', 'Corsa',       '{corsa classic}',                      null, null, '{manual}',           '{nafta,gnc}',    '{}'),
  ('Chevrolet', 'Classic',     '{}',                                   null, 2016, '{manual}',           '{nafta,gnc}',    '{LS,LT}'),
  ('Chevrolet', 'Agile',       '{}',                                   2009, 2016, '{manual}',           '{nafta}',        '{LS,LT,LTZ}'),
  ('Chevrolet', 'Spin',        '{}',                                   2013, null, '{manual,automatic}', '{nafta}',        '{LS,LT,LTZ,Activ,Premier}'),
  -- Renault
  ('Renault', 'Sandero',       '{}',                                   2008, null, '{manual,automatic}', '{nafta,gnc}',    '{Authentique,Expression,Privilège,Dynamique,Life,Zen,Intens,GT Line,RS}'),
  ('Renault', 'Stepway',       '{sandero stepway}',                    2009, null, '{manual,automatic}', '{nafta}',        '{Expression,Privilège,Zen,Intens}'),
  ('Renault', 'Logan',         '{}',                                   null, null, '{manual,automatic}', '{nafta,gnc}',    '{Authentique,Expression,Privilège,Life,Zen,Intens}'),
  ('Renault', 'Clio',          '{clio mio,clio mío}',                  null, 2016, '{manual}',           '{nafta,gnc}',    '{Pack,Authentique,Expression}'),
  ('Renault', 'Kangoo',        '{}',                                   null, null, '{manual}',           '{nafta,diesel}', '{Authentique,Confort,Life,Zen,Intens}'),
  ('Renault', 'Duster',        '{duster oroch}',                       2011, null, '{manual,automatic}', '{nafta,diesel}', '{Expression,Privilège,Dynamique,Zen,Intens,Iconic,Outsider}'),
  ('Renault', 'Kwid',          '{}',                                   2017, null, '{manual}',           '{nafta}',        '{Life,Zen,Intens,Outsider,Iconic}'),
  ('Renault', 'Captur',        '{}',                                   2017, 2023, '{manual,automatic}', '{nafta}',        '{Life,Zen,Intens}'),
  ('Renault', 'Fluence',       '{}',                                   2011, 2018, '{manual,automatic}', '{nafta}',        '{Confort,Luxe,Privilège,GT}'),
  ('Renault', 'Alaskan',       '{}',                                   2020, null, '{manual,automatic}', '{diesel}',       '{Confort,Emotion,Intens,Iconic}'),
  -- Fiat
  ('Fiat', 'Palio',            '{palio weekend,palio fire}',           1996, 2017, '{manual}',           '{nafta,gnc}',    '{Fire,ELX,Attractive,Essence,Sporting}'),
  ('Fiat', 'Siena',            '{grand siena}',                        1997, 2017, '{manual}',           '{nafta,gnc}',    '{Fire,EL,ELX,Attractive,Essence}'),
  ('Fiat', 'Cronos',           '{}',                                   2018, null, '{manual,automatic}', '{nafta}',        '{Like,Drive,Precision,S-Design}'),
  ('Fiat', 'Argo',             '{}',                                   2017, 2024, '{manual,automatic}', '{nafta}',        '{Drive,Precision,HGT,Trekking}'),
  ('Fiat', 'Mobi',             '{}',                                   2016, null, '{manual}',           '{nafta}',        '{Easy,Way,Like,Trekking}'),
  ('Fiat', 'Uno',              '{uno fire,novo uno}',                  null, 2021, '{manual}',           '{nafta,gnc}',    '{Fire,Way,Attractive,Sporting}'),
  ('Fiat', 'Punto',            '{}',                                   2007, 2017, '{manual,automatic}', '{nafta,diesel}', '{Attractive,Essence,Sporting}'),
  ('Fiat', 'Toro',             '{}',                                   2016, null, '{manual,automatic}', '{diesel,nafta}', '{Freedom,Volcano,Ranch,Ultra,Endurance}'),
  ('Fiat', 'Strada',           '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{Working,Adventure,Trekking,Freedom,Volcano,Ranch,Endurance}'),
  ('Fiat', 'Pulse',            '{}',                                   2021, null, '{manual,automatic}', '{nafta}',        '{Drive,Audace,Impetus,Abarth}'),
  -- Peugeot
  ('Peugeot', '208',           '{}',                                   2013, null, '{manual,automatic}', '{nafta}',        '{Like,Active,Allure,Feline,GT}'),
  ('Peugeot', '207',           '{207 compact}',                        2008, 2016, '{manual}',           '{nafta,diesel}', '{XR,XS,XT,Active,Allure,Feline}'),
  ('Peugeot', '206',           '{}',                                   1999, 2013, '{manual}',           '{nafta,diesel}', '{XR,XS,XT,Generation,Premium}'),
  ('Peugeot', '2008',          '{}',                                   2015, null, '{manual,automatic}', '{nafta}',        '{Active,Allure,Feline,GT,Sport}'),
  ('Peugeot', '308',           '{}',                                   2012, 2021, '{manual,automatic}', '{nafta,diesel}', '{Active,Allure,Feline,GT}'),
  ('Peugeot', '408',           '{}',                                   2011, 2021, '{manual,automatic}', '{nafta,diesel}', '{Allure,Feline,Sport}'),
  ('Peugeot', '3008',          '{}',                                   null, null, '{automatic}',        '{nafta,diesel}', '{Allure,Feline,GT Line,GT}'),
  ('Peugeot', 'Partner',       '{partner patagónica,partner patagonica}', null, null, '{manual}',        '{nafta,diesel}', '{Confort,Patagónica,Maxi}'),
  -- Citroën
  ('Citroën', 'C3',            '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Live,Feel,Shine,Exclusive,Tendance}'),
  ('Citroën', 'C3 Aircross',   '{c3aircross}',                         null, null, '{manual,automatic}', '{nafta}',        '{Live,Feel,Shine}'),
  ('Citroën', 'C4',            '{}',                                   2006, 2013, '{manual,automatic}', '{nafta,diesel}', '{X,SX,Exclusive}'),
  ('Citroën', 'C4 Lounge',     '{c4lounge}',                           2013, 2023, '{manual,automatic}', '{nafta,diesel}', '{Feel,Tendance,Shine}'),
  ('Citroën', 'C4 Cactus',     '{c4cactus}',                           2018, null, '{manual,automatic}', '{nafta}',        '{Live,Feel,Shine}'),
  ('Citroën', 'Berlingo',      '{}',                                   null, null, '{manual}',           '{nafta,diesel}', '{}'),
  -- Honda
  ('Honda', 'Civic',           '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EXL,EXS,Si,Type R}'),
  ('Honda', 'Fit',             '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,LX-L,EX,EX-L}'),
  ('Honda', 'City',            '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EXL}'),
  ('Honda', 'HR-V',            '{hrv,hr v}',                           2015, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EXL}'),
  ('Honda', 'CR-V',            '{crv,cr v}',                           null, null, '{automatic}',        '{nafta}',        '{LX,EX,EXL}'),
  ('Honda', 'WR-V',            '{wrv,wr v}',                           2017, null, '{manual,automatic}', '{nafta}',        '{EX,EXL}'),
  -- Nissan
  ('Nissan', 'March',          '{}',                                   2011, null, '{manual,automatic}', '{nafta}',        '{Active,Sense,Advance,Exclusive}'),
  ('Nissan', 'Versa',          '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Sense,Advance,Exclusive}'),
  ('Nissan', 'Sentra',         '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Sense,Advance,Exclusive,SR}'),
  ('Nissan', 'Note',           '{}',                                   2013, null, '{manual,automatic}', '{nafta}',        '{Sense,Advance,Exclusive}'),
  ('Nissan', 'Tiida',          '{}',                                   2007, 2013, '{manual,automatic}', '{nafta}',        '{Visia,Acenta,Tekna}'),
  ('Nissan', 'Kicks',          '{}',                                   2017, null, '{manual,automatic}', '{nafta}',        '{Sense,Advance,Exclusive}'),
  ('Nissan', 'Frontier',       '{}',                                   null, null, '{manual,automatic}', '{diesel}',       '{S,SE,XE,LE,Pro-4X,Platinum}'),
  -- Jeep
  ('Jeep', 'Renegade',         '{}',                                   2015, null, '{manual,automatic}', '{nafta,diesel}', '{Sport,Longitude,Limited,Trailhawk,Serie S}'),
  ('Jeep', 'Compass',          '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{Sport,Longitude,Limited,Trailhawk,Serie S}'),
  ('Jeep', 'Commander',        '{}',                                   2022, null, '{automatic}',        '{nafta,diesel}', '{Limited,Overland}'),
  -- Hyundai
  ('Hyundai', 'HB20',          '{hb 20}',                              null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Hyundai', 'Creta',         '{}',                                   2017, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Hyundai', 'Tucson',        '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('Hyundai', 'i30',           '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Hyundai', 'Santa Fe',      '{santafe}',                            null, null, '{automatic}',        '{nafta,diesel}', '{}'),
  -- Kia
  ('Kia', 'Picanto',           '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Kia', 'Rio',               '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Kia', 'Cerato',            '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Kia', 'Soul',              '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Kia', 'Sportage',          '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('Kia', 'Seltos',            '{}',                                   2020, null, '{automatic}',        '{nafta}',        '{}'),
  -- Audi
  ('Audi', 'A1',               '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Audi', 'A3',               '{a3 sportback,a3 sedan}',              null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Audi', 'A4',               '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Audi', 'Q2',               '{}',                                   null, null, '{automatic}',        '{nafta}',        '{}'),
  ('Audi', 'Q3',               '{}',                                   null, null, '{automatic}',        '{nafta}',        '{}'),
  ('Audi', 'Q5',               '{}',                                   null, null, '{automatic}',        '{nafta,diesel}', '{}'),
  -- BMW
  ('BMW', 'Serie 1',           '{serie1,116i,118i,120i,125i}',         null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('BMW', 'Serie 3',           '{serie3,318i,320i,328i,330i,335i}',    null, null, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('BMW', 'X1',                '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{}'),
  ('BMW', 'X3',                '{}',                                   null, null, '{automatic}',        '{nafta,diesel}', '{}'),
  -- Mercedes-Benz
  ('Mercedes-Benz', 'Clase A', '{a200,a250,a 200,a 250}',              null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Mercedes-Benz', 'Clase C', '{c200,c250,c300,c 200,c 250,c 300}',   null, null, '{automatic}',        '{nafta,diesel}', '{}'),
  ('Mercedes-Benz', 'GLA',     '{gla200,gla 200,gla250,gla 250}',      null, null, '{automatic}',        '{nafta}',        '{}'),
  ('Mercedes-Benz', 'Sprinter','{}',                                   null, null, '{manual,automatic}', '{diesel}',       '{}'),
  -- Mini
  ('Mini', 'Cooper',           '{cooper s,one}',                       null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Mini', 'Countryman',       '{cooper countryman}',                  null, null, '{manual,automatic}', '{nafta}',        '{}'),
  -- Subaru
  ('Subaru', 'Impreza',        '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Subaru', 'XV',             '{}',                                   null, null, '{automatic}',        '{nafta,hibrido}', '{}'),
  ('Subaru', 'Forester',       '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Subaru', 'Outback',        '{}',                                   null, null, '{automatic}',        '{nafta}',        '{}'),
  -- Mitsubishi
  ('Mitsubishi', 'Lancer',     '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Mitsubishi', 'ASX',        '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Mitsubishi', 'Outlander',  '{}',                                   null, null, '{automatic}',        '{nafta}',        '{}'),
  ('Mitsubishi', 'L200',       '{l 200}',                              null, null, '{manual,automatic}', '{diesel}',       '{}'),
  -- Suzuki
  ('Suzuki', 'Swift',          '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Suzuki', 'Fun',            '{}',                                   2003, 2011, '{manual}',           '{nafta}',        '{}'),
  ('Suzuki', 'Vitara',         '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Suzuki', 'Grand Vitara',   '{grandvitara}',                        null, null, '{manual,automatic}', '{nafta}',        '{}'),
  ('Suzuki', 'Jimny',          '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{}')
)
insert into public.vehicle_catalog (make, model, trim, aliases, year_from, year_to, transmissions, fuels)
select make, model, null, aliases::text[], year_from, year_to, transmissions::text[], fuels::text[]
  from models
union all
select m.make, m.model, t.trim, '{}', null, null, '{}', '{}'
  from models m, unnest(m.trims::text[]) as t (trim)
on conflict on constraint vehicle_catalog_unique do nothing;

-- Timing belt (true) or chain (false) of the model's usual engines: the
-- no_timing_belt red flag (sección 6.5). Same list as the F2 migration.
update public.vehicle_catalog c set timing_belt = v.belt
  from (values
    ('Volkswagen', 'Gol', true), ('Volkswagen', 'Gol Trend', true), ('Volkswagen', 'Suran', true),
    ('Volkswagen', 'Fox', true), ('Volkswagen', 'Saveiro', true), ('Volkswagen', 'Up', true),
    ('Ford', 'Fiesta', true), ('Ford', 'Ka', true), ('Ford', 'Focus', true), ('Ford', 'EcoSport', true),
    ('Chevrolet', 'Corsa', true), ('Chevrolet', 'Classic', true), ('Chevrolet', 'Agile', true),
    ('Chevrolet', 'Prisma', true), ('Chevrolet', 'Onix', true), ('Chevrolet', 'Spin', true),
    ('Renault', 'Clio', true), ('Renault', 'Sandero', true), ('Renault', 'Stepway', true),
    ('Renault', 'Logan', true), ('Renault', 'Kangoo', true), ('Renault', 'Duster', true),
    ('Fiat', 'Palio', true), ('Fiat', 'Siena', true), ('Fiat', 'Uno', true), ('Fiat', 'Punto', true),
    ('Peugeot', '206', true), ('Peugeot', '207', true), ('Peugeot', '208', true),
    ('Peugeot', 'Partner', true), ('Citroën', 'C3', true), ('Citroën', 'Berlingo', true),
    ('Toyota', 'Corolla', false), ('Toyota', 'Etios', false), ('Toyota', 'Yaris', false),
    ('Toyota', 'Hilux', false), ('Toyota', 'SW4', false), ('Honda', 'Civic', false),
    ('Honda', 'Fit', false), ('Honda', 'City', false), ('Honda', 'HR-V', false)
  ) as v (make, model, belt)
 where c.make = v.make and c.model = v.model and c.trim is null;
