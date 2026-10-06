-- New public regional catalogs and two Instagram feeds. Existing tuning wins.
-- All five passed public catalog/feed + detail probes on 2026-10-06.
-- Instagram uses an optional local session if anonymous access later stops working.
insert into public.sources (id, name, enabled, crawl_interval_seconds, priority, detail_interval_seconds) values
  ('mardelusados',   'Mardel Usados',      true,  3600, 60,  5),
  ('rosariogarage',  'Rosario Garage',     true,  3600, 70,  5),
  ('usadossantafe',  'Usados Santa Fe',     true,  3600, 80,  5),
  ('onlycarsusados', 'Only Cars Usados',   true, 7200, 90, 15),
  ('sc_clasificados','SC Clasificados',   true, 7200,100, 15)
on conflict (id) do nothing;
