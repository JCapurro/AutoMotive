-- Landing hero (20261219120000_landing_hero): the switch, what the hero shows
-- and the home's anonymous events.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select no_plan();

-- 1. The switch ships off, sharing half.
select is(
  (select value from public.app_config where key = 'landing_hero'),
  '{"enabled": false, "share": 50, "events_per_minute": 300}'::jsonb,
  'landing_hero: the migration seeds the test off, half and half'
);

-- 2. Who can call what.
select ok(not has_function_privilege('anon', 'public.landing_feed()', 'execute'), 'landing_feed: not for anon');
select ok(not has_function_privilege('authenticated', 'public.landing_feed()', 'execute'), 'landing_feed: not for signed-in users');
select ok(has_function_privilege('service_role', 'public.landing_feed()', 'execute'), 'landing_feed: for the service role');
select ok(has_function_privilege('anon', 'public.log_landing_event(text,text,text)', 'execute'), 'log_landing_event: for anon');

-- 3. landing_feed: counts every «high» listing of the last 24 h, shows only the solid ones.
insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000a1', 'hero-a@example.com'),
  ('00000000-0000-0000-0000-0000000000a2', 'hero-b@example.com'),
  ('00000000-0000-0000-0000-0000000000a3', 'hero-c@example.com');

insert into public.search_profiles (id, user_id, name, filters, created_at)
overriding system value values
  (990001, '00000000-0000-0000-0000-0000000000a1', 'Polo', '{"make": "Volkswagen", "model": "Polo"}', now()),
  (990002, '00000000-0000-0000-0000-0000000000a2', 'Polo', '{"make": "Volkswagen", "model": "Polo"}', now()),
  (990003, '00000000-0000-0000-0000-0000000000a3', 'Polo', '{"make": "Volkswagen", "model": "Polo"}', now()),
  (990004, '00000000-0000-0000-0000-0000000000a1', 'Focus', '{"make": "Ford", "model": "Focus"}', now());

insert into public.listings (id, source, external_id, url, title, make, model, trim, year, price, currency, price_usd, mileage_km, location_text, first_seen_at, status, price_partial)
overriding system value values
  (990001, 'kavak', 'hero-1', 'https://example.com/1', 'Polo', 'Volkswagen', 'Polo', 'Comfortline', 2018, 11457, 'USD', 11457, 86000, 'Buenos Aires', now() - interval '1 hour', 'active', false),
  -- much_cheaper: counted, never shown
  (990002, 'mercadolibre', 'hero-2', 'https://example.com/2', 'Gol', 'Volkswagen', 'Gol', null, 2013, 3000, 'USD', 3000, 150000, 'Rosario, Santa Fe', now() - interval '2 hours', 'active', false),
  -- few comparables: counted, never shown
  (990003, 'mercadolibre', 'hero-3', 'https://example.com/3', 'Focus', 'Ford', 'Focus', 'Trend', 2009, 4792, 'USD', 4792, 280000, 'Mendoza', now() - interval '3 hours', 'active', false),
  -- older than 24 h: not even counted
  (990004, 'mercadolibre', 'hero-4', 'https://example.com/4', 'Cruze', 'Chevrolet', 'Cruze', null, 2017, 9000, 'USD', 9000, 90000, 'Córdoba', now() - interval '30 hours', 'active', false),
  -- gone: not counted
  (990005, 'mercadolibre', 'hero-5', 'https://example.com/5', 'Vento', 'Volkswagen', 'Vento', null, 2016, 9000, 'USD', 9000, 90000, 'Córdoba', now() - interval '1 hour', 'gone', false),
  -- only a «good» match: not counted
  (990006, 'mercadolibre', 'hero-6', 'https://example.com/6', 'Civic', 'Honda', 'Civic', null, 2016, 9000, 'USD', 9000, 90000, 'Córdoba', now() - interval '1 hour', 'active', false);

insert into public.matches (search_profile_id, listing_id, score, level, price_ref, red_flags, score_breakdown, match_reasons, scoring_version) values
  (990001, 990001, 90, 'high', '{"n": 18, "median": 12880.79, "diff_pct": 11.05}', '[{"id": "no_owners", "severity": "info"}]', '{}', '[]', 'test'),
  (990002, 990001, 80, 'high', '{"n": 18, "median": 12880.79, "diff_pct": 11.05}', '[]', '{}', '[]', 'test'),
  (990001, 990002, 90, 'high', '{"n": 40, "median": 7000, "diff_pct": 57}', '[{"id": "much_cheaper", "severity": "warning"}]', '{}', '[]', 'test'),
  (990004, 990003, 90, 'high', '{"n": 5, "median": 5483, "diff_pct": 12.6}', '[]', '{}', '[]', 'test'),
  (990001, 990004, 90, 'high', '{"n": 30, "median": 10500, "diff_pct": 14}', '[]', '{}', '[]', 'test'),
  (990001, 990005, 90, 'high', '{"n": 30, "median": 10500, "diff_pct": 14}', '[]', '{}', '[]', 'test'),
  (990001, 990006, 70, 'good', '{"n": 30, "median": 10500, "diff_pct": 14}', '[]', '{}', '[]', 'test');

select is((public.landing_feed() ->> 'flagged_24h')::int >= 3, true, 'landing_feed: counts each «high» listing of the last 24 h once');
select is(
  (select jsonb_agg(r) from jsonb_array_elements(public.landing_feed() -> 'rows') r where r ->> 'source' = 'kavak' and r ->> 'make' = 'Volkswagen' and r ->> 'model' = 'Polo'),
  jsonb_build_array(jsonb_build_object(
    'make', 'Volkswagen', 'model', 'Polo', 'trim', 'Comfortline', 'year', 2018, 'km', 86000, 'usd', 11457,
    'median', 12881, 'n', 18, 'where', 'Buenos Aires', 'source', 'kavak',
    'seen_at', (select first_seen_at from public.listings where id = 990001))),
  'landing_feed: a solid listing is shown once, with its rounded median'
);
select is(
  (select count(*)::int from jsonb_array_elements(public.landing_feed() -> 'rows') r
    where (r ->> 'make', r ->> 'model') in (('Volkswagen', 'Gol'), ('Ford', 'Focus'), ('Chevrolet', 'Cruze'), ('Volkswagen', 'Vento'), ('Honda', 'Civic'))
      and r ->> 'where' in ('Rosario, Santa Fe', 'Mendoza', 'Córdoba')),
  0,
  'landing_feed: a serious flag, few comparables, an old, gone or merely good listing is never shown'
);
select ok(jsonb_array_length(public.landing_feed() -> 'rows') <= 4, 'landing_feed: at most four rows');
select ok(
  public.landing_feed() -> 'models' @> '[{"make": "Volkswagen", "model": "Polo"}]'::jsonb,
  'landing_feed: a model three people searched is listed'
);
select ok(
  not (public.landing_feed() -> 'models' @> '[{"make": "Ford", "model": "Focus"}]'::jsonb)
    or (select count(distinct user_id) from public.search_profiles where filters ->> 'make' = 'Ford' and filters ->> 'model' = 'Focus' and created_at > now() - interval '30 days') >= 3,
  'landing_feed: a model one person searched is not'
);

-- 4. log_landing_event, as a visitor.
set local role anon;
select throws_ok($$select public.landing_feed()$$, '42501', null, 'landing_feed: anon is refused');
select lives_ok($$select public.log_landing_event('landing_viewed', 'b')$$, 'log_landing_event: a visitor logs a view');
select lives_ok($$select public.log_landing_event('landing_search_started', 'a', 'typed')$$, 'log_landing_event: and how the search started');
select throws_ok($$select public.log_landing_event('signup_completed', 'a')$$, '22023', 'invalid_landing_event', 'log_landing_event: only its own names');
select throws_ok($$select public.log_landing_event('landing_viewed', 'c')$$, '22023', 'invalid_landing_variant', 'log_landing_event: only variants a and b');
select throws_ok($$select public.log_landing_event('landing_viewed', 'a', '<script>')$$, '22023', 'invalid_landing_how', 'log_landing_event: only known ways to start');
reset role;

select is(
  (select props from public.events where name = 'landing_search_started' order by id desc limit 1),
  '{"variant": "a", "how": "typed"}'::jsonb,
  'log_landing_event: stores the variant and how, nothing else'
);
select is(
  (select user_id from public.events where name = 'landing_viewed' order by id desc limit 1),
  null,
  'log_landing_event: a visitor has no user'
);

-- 5. Past the cap nothing is written.
update public.app_config set value = value || '{"events_per_minute": 2}' where key = 'landing_hero';
set local role anon;
select lives_ok($$select public.log_landing_event('landing_dialog_opened', 'b')$$, 'log_landing_event: past the cap it says nothing');
reset role;
select is(
  (select count(*)::int from public.events where name = 'landing_dialog_opened' and created_at > now() - interval '1 minute'),
  0,
  'log_landing_event: and writes nothing'
);

select * from finish();
rollback;
