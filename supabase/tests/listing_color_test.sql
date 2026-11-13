-- Filtro de color (migration 20261214120000_listing_color.sql,
-- docs/PLAN_FILTRO_COLOR.md sección 8). Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(44);

-- ---------------------------------------------------------------- schema and app_config
select has_column('public', 'listings', 'color', 'listings.color exists');
select throws_ok($$insert into public.listings (source, external_id, url, title, color)
                   values ('mercadolibre', 'LC-X', 'https://example.test/lc-x', 'x', 'rosa')$$,
                 '23514', null, 'listings.color: only the 8 codes');
select lives_ok($$insert into public.listings (source, external_id, url, title, color)
                  values ('mercadolibre', 'LC-Y', 'https://example.test/lc-y', 'y', 'gris')$$,
                '... a known code is stored');
select is((select value from public.app_config where key = 'color_vision'),
          '{"enabled": true, "daily_cap": 3000, "min_confidence": "media", "skip_sources": []}'::jsonb,
          'app_config.color_vision: on, 3000 per day, media confidence, no source skipped');
select has_table('public', 'color_vision_runs', 'color_vision_runs exists');
select is((select relrowsecurity from pg_class where oid = 'public.color_vision_runs'::regclass), true,
          'RLS is enabled on color_vision_runs');
select throws_ok($$insert into public.color_vision_runs (photos) values (11)$$,
                 '23514', null, 'color_vision_runs: at most 10 photos per call');

-- ---------------------------------------------------------------- search_colors
select is(public.search_colors('{}'), null, 'search_colors: no filter is null');
select is(public.search_colors('{"colors": []}'), null, '... an empty list too');
select is(public.search_colors('{"colors": null}'), null, '... and a JSON null');
select is(public.search_colors('{"colors": ["blanco", "gris"]}'), array['blanco', 'gris'],
          '... otherwise the codes, in order');

-- ---------------------------------------------------------------- listing_color_fits
select is(public.listing_color_fits('rojo', '{}', null), true, 'listing_color_fits: no filter passes');
select is(public.listing_color_fits('rojo', '{}', '{}'::text[]), true, '... an empty filter too');
select is(public.listing_color_fits(null, '{}', array['blanco']), true, '... an unknown color passes (sin confirmar)');
select is(public.listing_color_fits('blanco', '{}', array['blanco', 'gris']), true, '... the main color in the list passes');
select is(public.listing_color_fits('rojo', '{}', array['blanco', 'gris']), false, '... another color fails');
select is(public.listing_color_fits('rojo', null, array['blanco']), false, '... also without attributes');
select is(public.listing_color_fits('verde', '{"_color": {"candidates": [{"color": "verde", "prob": 70}, {"color": "blanco", "prob": 30}]}}',
                                    array['blanco']), true, '... a candidate in the list with prob 30 passes');
select is(public.listing_color_fits('verde', '{"_color": {"candidates": [{"color": "verde", "prob": 71}, {"color": "blanco", "prob": 29}]}}',
                                    array['blanco']), false, '... with prob 29 it doesn''t');
select is(public.listing_color_fits('verde', '{"_color": {"candidates": [{"color": "gris", "prob": 80}]}}', array['blanco']),
          false, '... a candidate of another color doesn''t help');
select is(public.listing_color_fits('verde', '{"_color": {"candidates": [{"color": "blanco", "prob": "90"}]}}', array['blanco']),
          false, '... nor a prob that is not a number');
select is(public.listing_color_fits('verde', '{"_color": {"candidates": {"color": "blanco"}}}', array['blanco']),
          false, '... nor candidates that are not a list');
select is(array(select p.provolatile::text from pg_proc p
                 where p.oid in ('public.search_colors(jsonb)'::regprocedure,
                                 'public.listing_color_fits(text,jsonb,text[])'::regprocedure)),
          array['i', 'i'], 'both helpers are immutable');
select is((select proconfig from pg_proc where oid = 'public.listing_color_fits(text,jsonb,text[])'::regprocedure),
          array['search_path=""'], '... with an empty search_path');
select is(has_function_privilege('authenticated', 'public.listing_color_fits(text,jsonb,text[])', 'execute')
          or has_function_privilege('anon', 'public.search_colors(jsonb)', 'execute'), false,
          '... and server-only');

-- ---------------------------------------------------------------- search_filters_problem
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "colors": ["blanco", "gris"]}'), null,
          'search_filters_problem: known color codes pass');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "colors": []}'), null,
          '... an empty list is no filter');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "colors": ["blanco", "rosa"]}'),
          'invalid_filters', '... an unknown code is rejected');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "colors": "blanco"}'),
          'invalid_filters', '... a string is rejected');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "colors": ["blanco", 1]}'),
          'invalid_filters', '... an element that is not text is rejected');
select is(public.search_filters_problem('{"make": false, "colors": ["blanco"]}'), 'invalid_filters',
          '... and the old rules still hold');

-- The trigger uses it when saving.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c0100000-0000-0000-0000-000000000001', 'authenticated', 'authenticated',
   'color@lc.test', now(), now());
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('c0100000-0000-0000-0000-000000000001', 'Rosa',
                           '{"make": "Ford", "model": "Fiesta", "colors": ["rosa"]}')$$,
                 '22023', 'invalid_filters', 'saving a search with an unknown color is rejected');

-- ---------------------------------------------------------------- preview_search
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency,
                             price_usd, color, attributes, first_seen_at)
overriding system value values
  (9871, 'mercadolibre', 'LC-1', 'https://example.test/lc-1', 'Pgcolor Prueba blanco', 'Pgcolor', 'Prueba', 2020,
   10000, 'USD', 10000, 'blanco', '{"_color": {"method": "source", "raw": "Blanco perla"}}', now()),
  (9872, 'mercadolibre', 'LC-2', 'https://example.test/lc-2', 'Pgcolor Prueba rojo', 'Pgcolor', 'Prueba', 2020,
   10000, 'USD', 10000, 'rojo', '{"_color": {"method": "text"}}', now() - interval '1 hour'),
  (9873, 'mercadolibre', 'LC-3', 'https://example.test/lc-3', 'Pgcolor Prueba', 'Pgcolor', 'Prueba', 2020,
   10000, 'USD', 10000, null, '{}', now() - interval '2 hours'),
  (9874, 'mercadolibre', 'LC-4', 'https://example.test/lc-4', 'Pgcolor Prueba verde', 'Pgcolor', 'Prueba', 2020,
   10000, 'USD', 10000, 'verde',
   '{"_color": {"method": "vision", "candidates": [{"color": "verde", "prob": 60}, {"color": "blanco", "prob": 35}]}}',
   now() - interval '3 hours'),
  (9875, 'mercadolibre', 'LC-5', 'https://example.test/lc-5', 'Pgcolor Prueba negro', 'Pgcolor', 'Prueba', 2020,
   10000, 'USD', 10000, 'negro',
   '{"_color": {"method": "vision", "candidates": [{"color": "negro", "prob": 71}, {"color": "blanco", "prob": 29}]}}',
   now() - interval '4 hours');

select is((public.preview_search('{"make": "Pgcolor", "model": "Prueba"}')->>'count')::int, 5,
          'preview without colors counts every color');
select is((public.preview_search('{"make": "Pgcolor", "model": "Prueba", "colors": ["blanco"]}')->>'count')::int, 3,
          'preview with blanco: the white one, the unknown one and the one with a white candidate at 35');
select is((public.preview_search('{"make": "Pgcolor", "model": "Prueba", "colors": ["rojo", "negro"]}')->>'count')::int, 3,
          '... with rojo or negro: those two and the unknown one');
select is((public.preview_search('{"make": "Pgcolor", "model": "Prueba", "colors": []}')->>'count')::int, 5,
          '... an empty list is no filter');
select is(public.preview_search('{"make": "Pgcolor", "model": "Prueba", "colors": ["blanco"]}')->'sample'->0->>'color',
          'blanco', '... the sample carries the color');

-- ---------------------------------------------------------------- missed_car (2.5): strict
set local session_replication_role = replica;
insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
  (9881, 'c0100000-0000-0000-0000-000000000001', 'Blanco', '{"make": "Pgcolor", "model": "Prueba", "colors": ["blanco"]}', true),
  (9882, 'c0100000-0000-0000-0000-000000000001', 'Cualquiera', '{"make": "Pgcolor", "model": "Prueba"}', true);
set local session_replication_role = origin;
insert into public.expired_search_matches (search_profile_id, listing_id, access_ended_at, level, diff_pct)
select s.id, v.listing_id, '2026-11-01 12:00+00', 'good', v.diff
  from (values (9881::bigint), (9882::bigint)) s (id)
 cross join (values (9871::bigint, 6::real), (9872, 30), (9873, 10), (9874, 25)) v (listing_id, diff);
select is((public.missed_car(9881, '2026-11-01 12:00+00')->>'listing_id')::bigint, 9873::bigint,
          'missed_car with blanco: not the red one, not the green one with a white candidate; the unknown one');
select is((public.missed_car(9882, '2026-11-01 12:00+00')->>'listing_id')::bigint, 9872::bigint,
          '... without colors, the best one');

-- ---------------------------------------------------------------- match_cards
select has_column('public', 'match_cards', 'color', 'match_cards.color exists');
select has_column('public', 'match_cards', 'color_method', 'match_cards.color_method exists');
select is(array(select attname::text from pg_attribute
                  where attrelid = 'public.match_cards'::regclass and attnum > 0 and not attisdropped
                  order by attnum desc limit 3), array['color_method', 'color', 'seller_unknown'],
          'match_cards: color and color_method appended after seller_unknown');
-- With plan limits enforced, guard_match_access would drop a free account's match.
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (9882, 9874, 80, 'good', '{}', '{}', 'test'), (9882, 9873, 70, 'good', '{}', '{}', 'test');
select is((select array[color, color_method] from public.match_cards where search_profile_id = 9882 and listing_id = 9874),
          array['verde', 'vision'], 'match_cards: the color and how it was decided');
select is((select array[color, color_method] from public.match_cards where search_profile_id = 9882 and listing_id = 9873),
          array[null, null]::text[], '... both null without the data');

select * from finish();
rollback;
