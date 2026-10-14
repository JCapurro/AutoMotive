-- deRuedas (www.deruedas.com.ar), clasificados de Cuyo: se busca por marca y modelo.
-- Inserción idempotente que no pisa ajustes del operador. El intervalo de fichas
-- respeta el Crawl-delay 5 de su robots.txt.
insert into public.sources (id, name, enabled, crawl_interval_seconds, priority, detail_interval_seconds) values
  ('deruedas', 'deRuedas', true, 3600, 140, 6)
on conflict (id) do nothing;
