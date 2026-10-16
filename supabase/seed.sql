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
  ('autocosmos',   'Autocosmos',           true,  1800, 50,  5),
  ('mardelusados', 'Mardel Usados',        true,  3600, 60,  5),
  ('rosariogarage','Rosario Garage',       true,  3600, 70,  5),
  ('usadossantafe','Usados Santa Fe',       true,  3600, 80,  5),
  ('onlycarsusados','Only Cars Usados',    true, 7200, 90, 15),
  ('sc_clasificados','SC Clasificados',    true, 7200,100, 15),
  ('autocity',      'Autocity',           true, 3600,110,  5),
  ('carone',        'Car One',            true, 3600,120,  5),
  ('gruporandazzo', 'Grupo Randazzo',     true, 3600,130,  5),
  ('deruedas',      'deRuedas',           true, 3600,140,  6)
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
  ('watchlist_matched',             '{"enabled": true, "unseen_hours": 6, "recheck_hours": 12, "max_age_days": 60, "per_source": 20}'),
  ('collector_failure_alert_after', '3'),
  ('plan_limits', '{
     "enforced": false,
     "free": {"max_profiles": 1, "max_visible_results": 100, "immediate_alerts_per_day": 3},
     "pass": {"max_profiles": 3, "immediate_alerts_per_day": 10, "model_less_search": true},
     "pro":  {"max_profiles": 20, "immediate_alerts_per_day": 50, "model_less_search": true}
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
  ('digest_top_n',                  '10'),
  ('llm_limits',                    '{"per_user_hour": 30}'),
  ('validation_criteria', '{
     "active_users_min": 30, "alert_open_min_pct": 30, "engagement_min_pct": 15,
     "retention_weeks": 3, "retention_min_pct": 40, "outcome_min_users": 3,
     "payment_intent_min_pct": 10, "activation_target_pct": 70
   }'),
  ('pro_cta',                       '{"min_alert_clicks": 3, "on_limits": ["max_profiles"]}'),
  ('pro_offer',                     '{"pro_monthly": {"price_usd": 15}, "pass_30": {"price_usd": 12}, "pass_90": {"price_usd": 25}}'),
  ('retention',                     '{"listing_days": 180}'),
  ('body_type_targets',             '{"sources": ["mercadolibre", "kavak"], "interval_seconds": 1800}')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- vehicle_catalog: most searched models in Argentina.
-- A model-level row (trim null) carries aliases, years, transmissions and fuels;
-- one extra row per known trim. Years are only filled where the range is well known.
-- ---------------------------------------------------------------------------

with models (make, model, aliases, year_from, year_to, transmissions, fuels, trims) as (values
  -- Volkswagen
  ('Volkswagen', 'Gol',        '{gol power}',                          1995, 2014, '{manual}',           '{nafta,gnc}',    '{CL,GL,GLD,GLi,GLS,Format,Dublin,Look,Deejay,Power,Power Plus,Trendline,Comfortline,Country,GTi}'),
  ('Volkswagen', 'Gol Trend',  '{goltrend}',                           2008, 2023, '{manual,automatic}', '{nafta,gnc}',    '{Pack I,Pack II,Pack III,Trendline,Serie,Comfortline,Highline,Sportline}'),
  ('Volkswagen', 'Suran',      '{suran cross}',                        2006, 2019, '{manual}',           '{nafta,gnc}',    '{Trendline,Comfortline,Highline,Track,Cross}'),
  ('Volkswagen', 'Fox',        '{crossfox}',                           2004, 2021, '{manual}',           '{nafta}',        '{Trendline,Comfortline,Highline}'),
  ('Volkswagen', 'Up',         '{up!,take up,move up,high up,cross up}', 2014, 2020, '{manual}',         '{nafta}',        '{Take up!,Move up!,High up!,Black up!,White up!,Cross up!}'),
  ('Volkswagen', 'Polo',       '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Classic,Format,Track,Trendline,Comfortline,Comfort Plus,Highline,GTS}'),
  ('Volkswagen', 'Virtus',     '{}',                                   2018, null, '{manual,automatic}', '{nafta}',        '{Trendline,Comfortline,Highline,Exclusive,GTS}'),
  ('Volkswagen', 'Vento',      '{}',                                   2006, null, '{manual,automatic}', '{nafta,diesel}', '{GL,GLX,VR6,Advance,Advance Plus,Luxury,Comfortline,Highline,Sportline,GLI}'),
  ('Volkswagen', 'Bora',       '{}',                                   2000, 2015, '{manual,automatic}', '{nafta,diesel}', '{Trendline,Comfortline,Highline}'),
  ('Volkswagen', 'Golf',       '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{GL,GLX,Format,Trendline,Comfortline,Highline,Sportline,GTI,R}'),
  ('Volkswagen', 'Saveiro',    '{}',                                   null, null, '{manual}',           '{nafta,gnc}',    '{Power,Trendline,Comfortline,Highline,Cross,Extreme,Robust}'),
  ('Volkswagen', 'Amarok',     '{}',                                   2010, null, '{manual,automatic}', '{diesel}',       '{Startline,Trendline,Comfortline,Highline,Highline Pack,Dark Label,V6,Extreme,Hero,Black Style}'),
  ('Volkswagen', 'T-Cross',    '{tcross,t cross}',                     2019, null, '{manual,automatic}', '{nafta}',        '{Sense,Trendline,Comfortline,Highline,Hero,Extreme}'),
  ('Volkswagen', 'Taos',       '{}',                                   2021, null, '{automatic}',        '{nafta}',        '{Comfortline,Highline,Hero}'),
  ('Volkswagen', 'Nivus',      '{}',                                   2020, null, '{automatic}',        '{nafta}',        '{Sense,Trendline,Comfortline,Highline,Hero,Outfit}'),
  -- Toyota
  ('Toyota', 'Corolla',        '{}',                                   null, null, '{manual,automatic}', '{nafta,hibrido}', '{XLI,XEI,SEG,GR-Sport,HEV}'),
  ('Toyota', 'Corolla Cross',  '{corollacross}',                       2021, null, '{automatic}',        '{nafta,hibrido}', '{XLI,XEI,SEG,GR-Sport}'),
  ('Toyota', 'Etios',          '{etios cross}',                        2013, 2023, '{manual,automatic}', '{nafta}',        '{X,XS,XLS,XLS Pack,Platinum}'),
  ('Toyota', 'Yaris',          '{}',                                   2018, null, '{manual,automatic}', '{nafta}',        '{XS,XLS,XLS Pack,XLS+,S}'),
  ('Toyota', 'Hilux',          '{}',                                   null, null, '{manual,automatic}', '{diesel,nafta}', '{DX,SR,SR5,SRV,SRX,Conquest,GR-Sport}'),
  ('Toyota', 'SW4',            '{sw 4,hilux sw4}',                     null, null, '{manual,automatic}', '{diesel,nafta}', '{SR,SRV,SRX,Diamond,GR-Sport}'),
  -- Ford
  ('Ford', 'Fiesta',           '{fiesta kinetic,fiesta kinetic design,fiesta max}', null, 2019, '{manual,automatic}', '{nafta,diesel}', '{LX,CLX,Ghia,Ambiente,Edge,Trend,S,S Plus,SE,SE Plus,Titanium,ST,SEL}'),
  ('Ford', 'Focus',            '{}',                                   null, 2019, '{manual,automatic}', '{nafta,diesel}', '{LX,CLX,Ambiente,Trend,Trend Plus,Edge,Ghia,Sport,S,SE,SE Plus,Titanium,ST}'),
  ('Ford', 'Ka',               '{ka+,ka plus}',                        null, 2021, '{manual}',           '{nafta}',        '{Image,Tattoo,Action,Fly,Fly Plus,Fly Viral,Viral,Pulse,Top Pulse,S,SE,SEL,Freestyle}'),
  ('Ford', 'EcoSport',         '{eco sport}',                          2003, 2022, '{manual,automatic}', '{nafta,diesel}', '{XL,XLS,XLT,XLT Plus,S,SE,Freestyle,Titanium,Storm}'),
  ('Ford', 'Ranger',           '{}',                                   null, null, '{manual,automatic}', '{diesel,nafta}', '{XL,XLS,XLT,Limited,FX4,Black,Raptor,Platinum}'),
  ('Ford', 'Territory',        '{}',                                   2020, null, '{automatic}',        '{nafta}',        '{Trend,SEL,Titanium}'),
  ('Ford', 'Maverick',         '{}',                                   2022, null, '{automatic}',        '{nafta,hibrido}', '{XLT,Lariat,Lariat FX4,Tremor}'),
  -- Chevrolet
  ('Chevrolet', 'Onix',        '{onix joy}',                           2013, null, '{manual,automatic}', '{nafta}',        '{Joy,LS,LT,LTZ,Activ,Effect,Premier,Premier II,RS}'),
  ('Chevrolet', 'Onix Plus',   '{onixplus}',                           2020, null, '{manual,automatic}', '{nafta}',        '{Joy,LS,LT,LTZ,Premier,Premier II,Midnight}'),
  ('Chevrolet', 'Prisma',      '{prisma joy}',                         2013, 2019, '{manual,automatic}', '{nafta}',        '{Joy,LS,LT,LTZ}'),
  ('Chevrolet', 'Cruze',       '{}',                                   2010, null, '{manual,automatic}', '{nafta,diesel}', '{LT,LTZ,LTZ Plus,Premier,Midnight,RS}'),
  ('Chevrolet', 'Tracker',     '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LS,LT,LTZ,LTZ Plus,Premier,Midnight,RS}'),
  ('Chevrolet', 'S10',         '{s-10,s 10}',                          null, null, '{manual,automatic}', '{diesel}',       '{DLX,Limited,WT,LS,LT,LTZ,Midnight,Z71,High Country}'),
  ('Chevrolet', 'Corsa',       '{corsa classic}',                      null, null, '{manual}',           '{nafta,gnc}',    '{City,Wind,Swing,GL,Super,GLS,CD,Sport,GSi}'),
  ('Chevrolet', 'Classic',     '{}',                                   null, 2016, '{manual}',           '{nafta,gnc}',    '{LS,LT,Spirit}'),
  ('Chevrolet', 'Agile',       '{}',                                   2009, 2016, '{manual}',           '{nafta}',        '{LS,LT,LTZ,Spirit,Effect}'),
  ('Chevrolet', 'Spin',        '{}',                                   2013, null, '{manual,automatic}', '{nafta}',        '{LS,LT,LTZ,Activ,Premier}'),
  -- Renault
  ('Renault', 'Sandero',       '{}',                                   2008, null, '{manual,automatic}', '{nafta,gnc}',    '{Authentique,Pack,Confort,Expression,Luxe,Privilège,Dynamique,Life,Zen,Intens,GT Line,RS}'),
  ('Renault', 'Stepway',       '{sandero stepway}',                    2009, null, '{manual,automatic}', '{nafta}',        '{Confort,Luxe,Rip Curl,Expression,Privilège,Dynamique,Zen,Intens}'),
  ('Renault', 'Logan',         '{}',                                   null, null, '{manual,automatic}', '{nafta,gnc}',    '{Authentique,Authentique Plus,Pack,Confort,Expression,Luxe,Privilège,Life,Zen,Intens}'),
  ('Renault', 'Clio',          '{clio mio,clio mío}',                  null, 2016, '{manual}',           '{nafta,gnc}',    '{RL,RN,RT,Authentique,Pack,Pack Plus,Confort,Expression,Privilège,Dynamique,GT Line,Sport}'),
  ('Renault', 'Kangoo',        '{}',                                   null, null, '{manual}',           '{nafta,diesel}', '{Authentique,Authentique Plus,Confort,Emotion,Sportway,Life,Zen,Intens,Stepway}'),
  ('Renault', 'Duster',        '{duster oroch}',                       2011, null, '{manual,automatic}', '{nafta,diesel}', '{Expression,Confort,Luxe,Dynamique,Privilège,Tech Road,Zen,Intens,Iconic,Outsider}'),
  ('Renault', 'Kwid',          '{}',                                   2017, null, '{manual}',           '{nafta}',        '{Life,Zen,Intens,Outsider,Iconic}'),
  ('Renault', 'Captur',        '{}',                                   2017, 2023, '{manual,automatic}', '{nafta}',        '{Life,Zen,Intens,Bose}'),
  ('Renault', 'Fluence',       '{}',                                   2011, 2018, '{manual,automatic}', '{nafta}',        '{Confort,Confort Plus,Luxe,Dynamique,Privilège,GT,GT2}'),
  ('Renault', 'Alaskan',       '{}',                                   2020, null, '{manual,automatic}', '{diesel}',       '{Confort,Emotion,Intens,Iconic,Outsider}'),
  -- Fiat
  ('Fiat', 'Palio',            '{palio weekend,palio fire}',           1996, 2017, '{manual}',           '{nafta,gnc}',    '{Young,S,Fire,EL,ED,EX,EDX,ELX,HL,HLX,Top Fire,Attractive,Essence,Sporting,Adventure,Trekking}'),
  ('Fiat', 'Siena',            '{grand siena}',                        1997, 2017, '{manual}',           '{nafta,gnc}',    '{S,Fire,EL,ED,EX,EDX,ELX,HL,HLX,Attractive,Essence}'),
  ('Fiat', 'Cronos',           '{}',                                   2018, null, '{manual,automatic}', '{nafta}',        '{Like,Drive,Drive Pack Conectividad,Drive Pack Plus,S-Design,Precision}'),
  ('Fiat', 'Argo',             '{}',                                   2017, 2024, '{manual,automatic}', '{nafta}',        '{Drive,Drive Pack Conectividad,Trekking,Precision,HGT}'),
  ('Fiat', 'Mobi',             '{}',                                   2016, null, '{manual}',           '{nafta}',        '{Easy,Easy Pack Top,Like,Way,Way On,Trekking}'),
  ('Fiat', 'Uno',              '{uno fire,novo uno}',                  null, 2021, '{manual}',           '{nafta,gnc}',    '{S,SL,SX,SCR,SCV,CS,CSL,Fire,Attractive,Way,Sporting}'),
  ('Fiat', 'Punto',            '{}',                                   2007, 2017, '{manual,automatic}', '{nafta,diesel}', '{ELX,HLX,Attractive,Essence,Sporting,T-Jet}'),
  ('Fiat', 'Toro',             '{}',                                   2016, null, '{manual,automatic}', '{diesel,nafta}', '{Endurance,Freedom,S-Design,Volcano,Ranch,Ultra}'),
  ('Fiat', 'Strada',           '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{Working,Fire,Trekking,Adventure,Adventure Locker,Endurance,Freedom,Volcano,Ranch,Ultra}'),
  ('Fiat', 'Pulse',            '{}',                                   2021, null, '{manual,automatic}', '{nafta}',        '{Drive,Audace,Impetus,Abarth}'),
  -- Peugeot
  ('Peugeot', '208',           '{}',                                   2013, null, '{manual,automatic}', '{nafta}',        '{Like,Active,Active Pack,Allure,Allure Pack,Allure Touchscreen,Roadtrip,Feline,XY,GT,GTi}'),
  ('Peugeot', '207',           '{207 compact}',                        2008, 2016, '{manual}',           '{nafta,diesel}', '{XR,Active,XS,Allure,XT,Premium,Feline,Quiksilver,GTi}'),
  ('Peugeot', '206',           '{}',                                   1999, 2013, '{manual}',           '{nafta,diesel}', '{XR,X-Line,Generation,XS,Allure,XT,Premium,Quiksilver,S16,RC}'),
  ('Peugeot', '2008',          '{}',                                   2015, null, '{manual,automatic}', '{nafta}',        '{Active,Allure,Allure Pack,In Concert,Feline,Sport,GT}'),
  ('Peugeot', '308',           '{}',                                   2012, 2021, '{manual,automatic}', '{nafta,diesel}', '{Active,Allure,Allure Plus,Allure NAV,Feline,Sport,GT,GTi}'),
  ('Peugeot', '408',           '{}',                                   2011, 2021, '{manual,automatic}', '{nafta,diesel}', '{Active,Allure,Allure Plus,Allure NAV,Feline,Sport}'),
  ('Peugeot', '3008',          '{}',                                   null, null, '{automatic}',        '{nafta,diesel}', '{Premium,Premium Plus,Allure,Allure Plus,Feline,GT Line,GT,GT Pack}'),
  ('Peugeot', 'Partner',       '{partner patagónica,partner patagonica}', null, null, '{manual}',        '{nafta,diesel}', '{Origin,Confort,Presence,Patagónica,VTC Plus,Maxi,Tepee}'),
  -- Citroën
  ('Citroën', 'C3',            '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Origine,X,SX,Live,Attraction,Tendance,Pack S,Feel,Feel Pack,Exclusive,Shine,XTR,First Edition}'),
  ('Citroën', 'C3 Aircross',   '{c3aircross}',                         null, null, '{manual,automatic}', '{nafta}',        '{Live,GLX,SX,Tendance,Feel,Feel Pack,Exclusive,Shine,XTR}'),
  ('Citroën', 'C4',            '{}',                                   2006, 2013, '{manual,automatic}', '{nafta,diesel}', '{X,SX,Tendance,Exclusive,VTR}'),
  ('Citroën', 'C4 Lounge',     '{c4lounge}',                           2013, 2023, '{manual,automatic}', '{nafta,diesel}', '{Live,Tendance,Feel,Feel Pack,Exclusive,Shine,S Edition}'),
  ('Citroën', 'C4 Cactus',     '{c4cactus}',                           2018, null, '{manual,automatic}', '{nafta}',        '{Live,Feel,Feel Pack,Feel Pack Plus,X-Series,Shine}'),
  ('Citroën', 'Berlingo',      '{}',                                   null, null, '{manual}',           '{nafta,diesel}', '{Business,First,Multispace,SX,XTR}'),
  -- Honda
  ('Honda', 'Civic',           '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{DX,LX,LXS,EX,EXS,EXL,EXT,Si,Type R,Advanced Hybrid}'),
  ('Honda', 'Fit',             '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,LX-L,EX,EX-L}'),
  ('Honda', 'City',            '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EXL}'),
  ('Honda', 'HR-V',            '{hrv,hr v}',                           2015, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EXL,EXT}'),
  ('Honda', 'CR-V',            '{crv,cr v}',                           null, null, '{automatic}',        '{nafta}',        '{LX,EX,EXL,EXT,Touring}'),
  ('Honda', 'WR-V',            '{wrv,wr v}',                           2017, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EXL}'),
  -- Nissan
  ('Nissan', 'March',          '{}',                                   2011, null, '{manual,automatic}', '{nafta}',        '{Visia,Visia Plus,Active,Acenta,Sense,Advance,Advance Media Tech,SR,Exclusive}'),
  ('Nissan', 'Versa',          '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Sense,V-Drive,V-Drive Plus,Advance,SR,Exclusive}'),
  ('Nissan', 'Sentra',         '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Sense,Advance,SR,Exclusive}'),
  ('Nissan', 'Note',           '{}',                                   2013, null, '{manual,automatic}', '{nafta}',        '{Sense,Advance,Exclusive}'),
  ('Nissan', 'Tiida',          '{}',                                   2007, 2013, '{manual,automatic}', '{nafta}',        '{Visia,Acenta,Tekna}'),
  ('Nissan', 'Kicks',          '{}',                                   2017, null, '{manual,automatic}', '{nafta}',        '{Sense,Advance,Advance Plus,Exclusive,Play}'),
  ('Nissan', 'Frontier',       '{}',                                   null, null, '{manual,automatic}', '{diesel}',       '{S,XE,X-Gear,SE,LE,Pro-4X,Platinum}'),
  -- Jeep
  ('Jeep', 'Renegade',         '{}',                                   2015, null, '{manual,automatic}', '{nafta,diesel}', '{Sport,Longitude,Limited,Serie S,Willys,Trailhawk}'),
  ('Jeep', 'Compass',          '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{Sport,Longitude,Longitude Plus,Limited,Limited Plus,Serie S,Trailhawk,Blackhawk}'),
  ('Jeep', 'Commander',        '{}',                                   2022, null, '{automatic}',        '{nafta,diesel}', '{Limited,Limited Plus,Overland,Blackhawk}'),
  -- Hyundai
  ('Hyundai', 'HB20',          '{hb 20}',                              null, null, '{manual,automatic}', '{nafta}',        '{Comfort Plus,Platinum,Platinum Safety}'),
  ('Hyundai', 'Creta',         '{}',                                   2017, null, '{manual,automatic}', '{nafta}',        '{GL,GL Connect,GLS,Limited,Safety,Safety+,Ultimate}'),
  ('Hyundai', 'Tucson',        '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{GL,GLS,Style,Premium,GLS Premium,Full Premium,Safety,Safety+,Ultimate}'),
  ('Hyundai', 'i30',           '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{GL,GLS,GLS Premium}'),
  ('Hyundai', 'Santa Fe',      '{santafe}',                            null, null, '{automatic}',        '{nafta,diesel}', '{GL,GLS,Premium,GLS Premium,Full Premium,Style}'),
  -- Kia
  ('Kia', 'Picanto',           '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EX Pack,EX Full,GT Line,X-Line}'),
  ('Kia', 'Rio',               '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LS,LX,EX,EX Pack,SX}'),
  ('Kia', 'Cerato',            '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,EX,SX,SX Plus,SX GT Line,Koup}'),
  ('Kia', 'Soul',              '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{LX,EX,EX Pack,SX}'),
  ('Kia', 'Sportage',          '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{LX,EX,EX Premium,SX,GT Line,X-Line}'),
  ('Kia', 'Seltos',            '{}',                                   2020, null, '{automatic}',        '{nafta}',        '{LX,EX}'),
  -- Audi
  ('Audi', 'A1',               '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Attraction,Ambition,Sport,S Line,Advanced,S1}'),
  ('Audi', 'A3',               '{a3 sportback,a3 sedan}',              null, null, '{manual,automatic}', '{nafta}',        '{Attraction,Ambition,S Line,Advanced,S3,RS3}'),
  ('Audi', 'A4',               '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{Attraction,Ambition,Sport,S Line,Advanced,Allroad,S4,RS4}'),
  ('Audi', 'Q2',               '{}',                                   null, null, '{automatic}',        '{nafta}',        '{Design,Sport,S Line,Advanced}'),
  ('Audi', 'Q3',               '{}',                                   null, null, '{automatic}',        '{nafta}',        '{Attraction,Ambition,S Line,Advanced,Advanced Plus,RS Q3}'),
  ('Audi', 'Q5',               '{}',                                   null, null, '{automatic}',        '{nafta,diesel}', '{Attraction,Ambition,S Line,Advanced,SQ5}'),
  -- BMW
  ('BMW', 'Serie 1',           '{serie1,116i,118i,120i,125i}',         null, null, '{manual,automatic}', '{nafta}',        '{116i,118i,120i,125i,130i,135i,M135i,M140i,118d,120d}'),
  ('BMW', 'Serie 3',           '{serie3,318i,320i,328i,330i,335i}',    null, null, '{manual,automatic}', '{nafta,diesel}', '{316i,318i,320i,323i,325i,328i,330i,335i,340i,320d,330d,330e,M3}'),
  ('BMW', 'X1',                '{}',                                   null, null, '{manual,automatic}', '{nafta,diesel}', '{sDrive18i,sDrive20i,xDrive20i,xDrive25i,xDrive28i,sDrive18d,sDrive20d,xDrive20d,xDrive23d}'),
  ('BMW', 'X3',                '{}',                                   null, null, '{automatic}',        '{nafta,diesel}', '{2.5i,2.5si,3.0i,3.0si,xDrive20i,xDrive28i,xDrive30i,xDrive35i,xDrive20d,xDrive30d,M40i,X3 M}'),
  -- Mercedes-Benz
  ('Mercedes-Benz', 'Clase A', '{a200,a250,a 200,a 250}',              null, null, '{manual,automatic}', '{nafta}',        '{A160,A170,A190,A200,A250,A35 AMG,A45 AMG}'),
  ('Mercedes-Benz', 'Clase C', '{c200,c250,c300,c 200,c 250,c 300}',   null, null, '{automatic}',        '{nafta,diesel}', '{C180,C200,C220 CDI,C230,C240,C250,C280,C300,C350,C43 AMG,C63 AMG}'),
  ('Mercedes-Benz', 'GLA',     '{gla200,gla 200,gla250,gla 250}',      null, null, '{automatic}',        '{nafta}',        '{GLA 200,GLA 250,GLA 35 AMG,GLA 45 AMG}'),
  ('Mercedes-Benz', 'Sprinter','{}',                                   null, null, '{manual,automatic}', '{diesel}',       '{310D,312D,412D,311 CDI,313 CDI,411 CDI,413 CDI,415 CDI,515 CDI,516 CDI,417 CDI,517 CDI,Street}'),
  -- Mini
  ('Mini', 'Cooper',           '{cooper s,one}',                       null, null, '{manual,automatic}', '{nafta}',        '{One,Cooper S,John Cooper Works,Cooper SE}'),
  ('Mini', 'Countryman',       '{cooper countryman}',                  null, null, '{manual,automatic}', '{nafta}',        '{One,Cooper,Cooper D,Cooper S,Cooper SD,John Cooper Works,Cooper SE}'),
  -- Subaru
  ('Subaru', 'Impreza',        '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{GL,GX,RS,R,XS,Sport,Limited,WRX,WRX STI}'),
  ('Subaru', 'XV',             '{}',                                   null, null, '{automatic}',        '{nafta,hibrido}', '{R,XS,Dynamic,Limited}'),
  ('Subaru', 'Forester',       '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{GL,XS,XT,Sport,Dynamic,Limited}'),
  ('Subaru', 'Outback',        '{}',                                   null, null, '{automatic}',        '{nafta}',        '{Premium,Limited,Touring,3.6R}'),
  -- Mitsubishi
  ('Mitsubishi', 'Lancer',     '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{GLi,GLX,GLS,GT,Ralliart,Evolution}'),
  ('Mitsubishi', 'ASX',        '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{GLX,GLS,GLS Full}'),
  ('Mitsubishi', 'Outlander',  '{}',                                   null, null, '{automatic}',        '{nafta}',        '{LS,XLS,GLS,GT,Sport,PHEV}'),
  ('Mitsubishi', 'L200',       '{l 200}',                              null, null, '{manual,automatic}', '{diesel}',       '{GL,GLX,GLS,Outdoor,Sportero,Triton,Sport,Katana}'),
  -- Suzuki
  ('Suzuki', 'Swift',          '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{GA,GL,GLX,GTi,Sport}'),
  ('Suzuki', 'Fun',            '{}',                                   2003, 2011, '{manual}',           '{nafta}',        '{}'),
  ('Suzuki', 'Vitara',         '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{JX,JLX,Sidekick,GL,GLX,GLX AllGrip}'),
  ('Suzuki', 'Grand Vitara',   '{grandvitara}',                        null, null, '{manual,automatic}', '{nafta}',        '{JX,JLX,GL,GLX,XL-7,Sport}'),
  ('Suzuki', 'Jimny',          '{}',                                   null, null, '{manual,automatic}', '{nafta}',        '{JX,JLX,GL,GLX}')
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

-- Body types (docs/CARROCERIA.md): the model's possible bodies, most common
-- first; one value = certain. Every row of the model, trims included. Same
-- list as migration 20261030120100_catalog_body_types.sql, which explains it.
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
