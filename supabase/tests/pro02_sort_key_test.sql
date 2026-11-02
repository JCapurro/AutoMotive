-- PRO-02 revisión 5 (migration 20261201120000_pro02_sort_key_plausible.sql):
-- my_margin_sort_keys returns low = null for a margin_ref the web hides
-- (web/lib/margin-view.ts plausiblePrice, worker margin.plausible), so the
-- «Mayor margen estimado» order puts it last. Run with: supabase test db
-- Run in an isolated local database; all fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

select ok(not has_function_privilege('anon', 'public.my_margin_sort_keys(bigint)', 'execute'), 'my_margin_sort_keys: not for anon');
select ok(has_function_privilege('authenticated', 'public.my_margin_sort_keys(bigint)', 'execute'), 'my_margin_sort_keys: for authenticated');
select ok((select prosecdef from pg_proc where oid = 'public.my_margin_sort_keys(bigint)'::regprocedure), '... security definer');

-- A laxer config than the default: the stored refs without bounds are still
-- judged by {0.4, 3}, as the web and the worker's plausible() do.
update public.app_config set value = value || '{"plausible_ratio": {"min": 0.1, "max": 10}}'::jsonb where key = 'dealer_margin';

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c0250000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'pro@pro02sk.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c0250000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'pass@pro02sk.test', now(), now());
update public.profiles p set plan = v.plan::public.user_plan, plan_expires_at = now() + interval '30 days'
  from (values ('c0250000-0000-0000-0000-000000000001'::uuid, 'pro'),
               ('c0250000-0000-0000-0000-000000000002'::uuid, 'pass')) v (id, plan)
 where p.id = v.id;

insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (9981, 'c0250000-0000-0000-0000-000000000001', 'Orden Pro', '{"make": "Pgtap", "model": "Orden"}', now()),
  (9982, 'c0250000-0000-0000-0000-000000000002', 'Orden Particular', '{"make": "Pgtap", "model": "Orden"}', now());

-- 9980xx: one listing per case; the gone ones are the matches the worker's
-- rescore_queue never re-scores (the bug: they kept the old ref).
insert into public.listings (id, source, external_id, url, title, make, model, price, currency, price_usd, status)
overriding system value
select 998000 + i, 'mercadolibre', 'PRO02SK-' || i, 'https://example.test/pro02sk-' || i, 'Pgtap Orden ' || i,
       'Pgtap', 'Orden', 10000, 'USD', 10000, case when i between 20 and 22 then 'gone' else 'active' end::public.listing_status
  from generate_series(1, 33) i;

-- median 11000: 0.4x = 4400, 3x = 33000.
insert into public.matches (id, search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version, margin_ref)
overriding system value values
  (99810001, 9981, 998001, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "plausible_ratio": {"min": 0.4, "max": 3}, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810002, 9981, 998002, 50, 'good', '{}', '{}', 'test', '{"v": 1, "status": "ok", "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 310, "max": 400}}'),
  (99810003, 9981, 998003, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 33100, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": -23000, "max": -22000}}'),
  (99810004, 9981, 998004, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 4000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 6000, "max": 6100}}'),
  (99810005, 9981, 998005, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 33000.01, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": -22100, "max": -22000}}'),
  (99810006, 9981, 998006, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 33000.02, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": -22100, "max": -22000}}'),
  (99810007, 9981, 998007, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 4400, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 5600, "max": 5700}}'),
  (99810008, 9981, 998008, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 4399.98, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 5600, "max": 5700}}'),
  (99810009, 9981, 998009, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 50000, "dealer_median": 11000, "plausible_ratio": {"min": 0.2, "max": 5}, "dealer_n": 8, "gross_margin_usd": {"min": -40000, "max": -39000}}'),
  (99810010, 9981, 998010, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 25000, "dealer_median": 11000, "plausible_ratio": {"min": 0.5, "max": 2}, "dealer_n": 8, "gross_margin_usd": {"min": -15000, "max": -14000}}'),
  (99810011, 9981, 998011, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 40000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": -30000, "max": -29000}}'),
  (99810012, 9981, 998012, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 40000, "dealer_median": 11000, "plausible_ratio": {"min": 1.5, "max": 10}, "dealer_n": 8, "gross_margin_usd": {"min": -30000, "max": -29000}}'),
  (99810013, 9981, 998013, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 0, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810014, 9981, 998014, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": null, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810015, 9981, 998015, 50, 'good', '{}', '{}', 'test', '{"v": 1, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810016, 9981, 998016, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": "10000", "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810017, 9981, 998017, 50, 'good', '{}', '{}', 'test', '{"v": 1, "status": "few_dealers", "dealer_n": 2, "min_n": 5}'),
  (99810018, 9981, 998018, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": "300", "max": 400}}'),
  (99810019, 9981, 998019, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": -5, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  -- Saved matches of gone listings: a plausible margin, one below 0.4x
  -- (the highest margin) and one without margin.
  (99810020, 9981, 998020, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810021, 9981, 998021, 90, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 2000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 8000, "max": 8100}}'),
  (99810022, 9981, 998022, 70, 'good', '{}', '{}', 'test', null),
  -- What the web's asMarginRef also requires (the worker's plausible() too for
  -- the status): a JSON null status is not ok; gross_margin_usd.max and
  -- dealer_n numbers.
  (99810023, 9981, 998023, 50, 'good', '{}', '{}', 'test', '{"v": 1, "status": null, "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810024, 9981, 998024, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300}}'),
  (99810025, 9981, 998025, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810026, 9981, 998026, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "dealer_n": "8", "gross_margin_usd": {"min": 300, "max": "400"}}'),
  (99810027, 9981, 998027, 50, 'good', '{}', '{}', 'test', '{"v": 1, "status": "ok", "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 305, "max": 400}}'),
  -- Exactly at a bound to the cent where float8 (JS, Python) and exact
  -- numeric disagree: 3 x 23542.57 + 0.01 = 70627.71999999999 and
  -- 0.4 x 10000.7 - 0.01 = 4000.2700000000004 in float, so the web hides both.
  (99810028, 9981, 998028, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 70627.72, "dealer_median": 23542.57, "dealer_n": 8, "gross_margin_usd": {"min": -47100, "max": -47000}}'),
  (99810029, 9981, 998029, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 4000.27, "dealer_median": 10000.7, "dealer_n": 8, "gross_margin_usd": {"min": 5900, "max": 6000}}'),
  -- ... and with their own bounds {0.4, 3}, compared in float8 too.
  (99810030, 9981, 998030, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 70627.72, "dealer_median": 23542.57, "dealer_n": 8, "plausible_ratio": {"min": 0.4, "max": 3}, "gross_margin_usd": {"min": -47100, "max": -47000}}'),
  -- Beyond float8's range: not finite for the web (JSON.parse gives Infinity
  -- or 0); null, never a cast error.
  (99810031, 9981, 998031, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 1e400, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810032, 9981, 998032, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 1e-400, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99810033, 9981, 998033, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 1e400}}'),
  (99820001, 9982, 998001, 50, 'good', '{}', '{}', 'test', '{"v": 1, "asking_usd": 10000, "dealer_median": 11000, "dealer_n": 8, "gross_margin_usd": {"min": 300, "max": 400}}');

insert into public.user_listing_interactions (user_id, listing_id, status, saved) values
  ('c0250000-0000-0000-0000-000000000001', 998020, 'purchased', true),
  ('c0250000-0000-0000-0000-000000000001', 998021, 'purchased', true),
  ('c0250000-0000-0000-0000-000000000001', 998022, 'purchased', true);

-- ---------------------------------------------------------------- the Pro
set local role authenticated;
set local request.jwt.claims = '{"sub": "c0250000-0000-0000-0000-000000000001", "role": "authenticated"}';

create temp table k on commit drop as select * from public.my_margin_sort_keys(9981);

select is((select count(*)::int from k), 32, 'one row per match with a margin_ref (the null one is not there)');
select is((select low from k where match_id = 99810001), 300::numeric, 'plausible, with its own bounds: the low end');
select is((select low from k where match_id = 99810002), 310::numeric, 'plausible, status ok, a ref from before the guard (no bounds): the low end');
select is((select low from k where match_id = 99810003), null, 'above 3x: null');
select is((select low from k where match_id = 99810004), null, 'below 0.4x: null');
select is((select low from k where match_id = 99810005), -22100::numeric, 'exactly 3x plus the 0.01 USD slack: plausible');
select is((select low from k where match_id = 99810006), null, '... 0.02 above 3x: null');
select is((select low from k where match_id = 99810007), 5600::numeric, 'exactly 0.4x: plausible');
select is((select low from k where match_id = 99810008), null, '... 0.02 below 0.4x: null');
select is((select low from k where match_id = 99810009), -40000::numeric, 'its own bounds {0.2, 5}: 4.5x is plausible');
select is((select low from k where match_id = 99810010), null, 'its own bounds {0.5, 2}: 2.3x is not, though the default would let it');
select is((select low from k where match_id = 99810011), null,
          'no bounds of its own and a laxer config {0.1, 10}: judged by the default, as the web hides it');
select is((select low from k where match_id = 99810012), null, 'invalid own bounds (min >= 1): the default');
select is((select low from k where match_id = 99810013), null, 'dealer_median 0: null');
select is((select low from k where match_id = 99810014), null, 'dealer_median null: null');
select is((select low from k where match_id = 99810015), null, 'no asking_usd: null');
select is((select low from k where match_id = 99810016), null, 'asking_usd not a number: null (no cast error)');
select is((select low from k where match_id = 99810017), null, 'few_dealers: null');
select is((select low from k where match_id = 99810018), null, 'gross_margin_usd.min not a number: null (no cast error)');
select is((select low from k where match_id = 99810019), null, 'dealer_median negative: null');
select is((select low from k where match_id = 99810023), null, 'status JSON null: null (the web and the worker hide it)');
select is((select low from k where match_id = 99810024), null, 'no gross_margin_usd.max: null');
select is((select low from k where match_id = 99810025), null, 'no dealer_n: null');
select is((select low from k where match_id = 99810026), null, 'gross_margin_usd.max and dealer_n not numbers: null (no cast error)');
select is((select low from k where match_id = 99810027), 305::numeric, 'status "ok" with every field: the low end');
select is((select low from k where match_id = 99810028), null, '3x + 0.01 exact in numeric but not in float8: null, as the web');
select is((select low from k where match_id = 99810029), null, '0.4x - 0.01 exact in numeric but not in float8: null, as the web');
select is((select low from k where match_id = 99810030), null, '... with its own bounds too');
select is((select low from k where match_id = 99810031), null, 'asking_usd beyond float8: null');
select is((select low from k where match_id = 99810032), null, 'dealer_median below float8 (0 in JS): null');
select is((select low from k where match_id = 99810033), null, 'gross_margin_usd.max beyond float8: null');

select results_eq($$select listing_id from public.search_results(9981, 'purchased', 'margin') limit 1$$,
                  $$values (998020::bigint)$$,
                  'search_results purchased by margin: the plausible one first, not the implausible one (the highest margin, gone)');
select set_eq($$select listing_id from public.search_results(9981, 'purchased', 'margin') offset 1$$,
              $$values (998021::bigint), (998022::bigint)$$,
              '... the implausible one last, with the one without margin');
select results_eq($$select listing_id from public.search_results(9981, 'saved', 'margin') limit 1$$,
                  $$values (998020::bigint)$$, '... saved too');
select results_eq($$select listing_id from public.search_results(9981, 'all', 'margin') limit 5$$,
                  $$values (998007::bigint), (998002::bigint), (998027::bigint), (998001::bigint), (998005::bigint)$$,
                  'search_results all by margin: only the plausible ones first, highest low end first');
select is((select count(*)::int from public.my_margin_sort_keys(9982)), 0, 'never another user''s search');
reset role;

-- ---------------------------------------------------------------- the Particular
set local role authenticated;
set local request.jwt.claims = '{"sub": "c0250000-0000-0000-0000-000000000002", "role": "authenticated"}';
select is((select count(*)::int from public.my_margin_sort_keys(9982)), 0, 'nothing without the feature');
reset role;

select * from finish();
rollback;
