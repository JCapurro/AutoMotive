-- Public used-car catalogs; do not override existing operator tuning.
insert into public.sources (id, name, enabled, crawl_interval_seconds, priority, detail_interval_seconds) values
  ('autocity',      'Autocity',       true, 3600,110,5),
  ('carone',        'Car One',        true, 3600,120,5),
  ('gruporandazzo', 'Grupo Randazzo', true, 3600,130,5)
on conflict (id) do nothing;
