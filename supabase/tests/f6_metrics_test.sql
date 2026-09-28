-- F6 metrics, plan limits and the Pro waitlist (migration 20261003120000_f6_backoffice_metrics.sql).
-- Run with: supabase test db
--
-- The views aggregate the whole database, so the test starts from an empty one
-- (inside the transaction; the rollback brings everything back) and seeds a
-- small pilot: five users, one admin, alerts on every channel and the events
-- the web and the worker record.
begin;
create extension if not exists pgtap with schema extensions;
select plan(52);

delete from auth.users;

-- Known thresholds and limits, whatever the database has.
update public.app_config set value = '{
  "active_users_min": 3, "alert_open_min_pct": 30, "engagement_min_pct": 90,
  "retention_weeks": 3, "retention_min_pct": 40, "outcome_min_users": 3,
  "payment_intent_min_pct": 10, "activation_target_pct": 70}'
 where key = 'validation_criteria';
update public.app_config set value = '{
  "enforced": false,
  "free": {"max_profiles": 1, "max_visible_results": 50, "immediate_alerts": false},
  "pro":  {"max_profiles": 10, "immediate_alerts": true},
  "pass": {"max_profiles": 10, "immediate_alerts": true}}'
 where key = 'plan_limits';
update public.app_config set value = '10' where key = 'alerts_max_per_user_day';
update public.app_config set value = '{"min_alert_clicks": 3, "on_limits": ["max_profiles"]}'
 where key = 'pro_cta';

-- ---------------------------------------------------------------- users
-- u1..u4 signed up on the web; u5 is Telegram-only (old wizard, no email).
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '61111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'u1@f6.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', '62222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'u2@f6.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', '63333333-3333-3333-3333-333333333333', 'authenticated', 'authenticated', 'u3@f6.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', '64444444-4444-4444-4444-444444444444', 'authenticated', 'authenticated', 'u4@f6.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', '65555555-5555-5555-5555-555555555555', 'authenticated', 'authenticated', null, now(), now()),
  ('00000000-0000-0000-0000-000000000000', '6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'authenticated', 'authenticated', 'admin@f6.test', now(), now());

update public.profiles p set created_at = now() - v.age, plan = v.plan::public.user_plan,
                             plan_expires_at = v.expires, role = v.role::public.user_role
  from (values
    ('61111111-1111-1111-1111-111111111111'::uuid, interval '30 days', 'free', null::timestamptz, 'user'),
    ('62222222-2222-2222-2222-222222222222'::uuid, interval '30 days', 'free', null, 'user'),
    ('63333333-3333-3333-3333-333333333333'::uuid, interval '10 days', 'pro',  now() - interval '1 day', 'user'),
    ('64444444-4444-4444-4444-444444444444'::uuid, interval '5 days',  'free', null, 'user'),
    ('65555555-5555-5555-5555-555555555555'::uuid, interval '40 days', 'pass', now() + interval '20 days', 'user'),
    ('6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid, interval '40 days', 'free', null, 'admin')
  ) as v (id, age, plan, expires, role)
 where p.id = v.id;

-- Daily searches: immediate ones would log plan_limit_hit (tested at the end).
insert into public.search_profiles (id, user_id, name, filters, notification_frequency, created_at, bootstrapped_at)
overriding system value values
  (9601, '61111111-1111-1111-1111-111111111111', 'u1', '{"make": "Pgtap", "model": "F6"}', 'daily', now() - interval '25 days', now()),
  (9602, '62222222-2222-2222-2222-222222222222', 'u2', '{"make": "Pgtap", "model": "F6"}', 'daily', now() - interval '22 days', now()),
  (9603, '63333333-3333-3333-3333-333333333333', 'u3', '{"make": "Pgtap", "model": "F6"}', 'daily', now() - interval '10 days', now()),
  (9605, '65555555-5555-5555-5555-555555555555', 'u5', '{"make": "Pgtap", "model": "F6"}', 'daily', now() - interval '30 days', now()),
  (9606, '6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'admin', '{"make": "Pgtap", "model": "F6"}', 'daily', now() - interval '30 days', now());

insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd)
overriding system value values
  (9601, 'mercadolibre', 'F6-1', 'https://example.test/f6-1', 'Pgtap F6 1', 'Pgtap', 'F6', 2017, 10000, 'USD', 10000),
  (9602, 'mercadolibre', 'F6-2', 'https://example.test/f6-2', 'Pgtap F6 2', 'Pgtap', 'F6', 2017, 11000, 'USD', 11000),
  (9603, 'kavak',        'F6-3', 'https://example.test/f6-3', 'Pgtap F6 3', 'Pgtap', 'F6', 2018, 12000, 'USD', 12000),
  (9604, 'kavak',        'F6-4', 'https://example.test/f6-4', 'Pgtap F6 4', 'Pgtap', 'F6', 2016,  9000, 'USD',  9000),
  (9605, 'v6',           'F6-5', 'https://example.test/f6-5', 'Pgtap F6 5', 'Pgtap', 'F6', 2016,  9500, 'USD',  9500);

-- u1's search got its first 🟢 a day after it was created; u2's never did.
insert into public.matches (id, search_profile_id, listing_id, score, level, score_breakdown, match_reasons,
                            scoring_version, generated_at) overriding system value values
  (9601, 9601, 9601, 90, 'high',  '{}', '{}', 'test', now() - interval '24 days'),
  (9602, 9601, 9602, 72, 'good',  '{}', '{}', 'test', now() - interval '20 days'),
  (9603, 9601, 9603, 55, 'match', '{}', '{}', 'test', now() - interval '20 days'),
  (9604, 9602, 9601, 60, 'match', '{}', '{}', 'test', now() - interval '21 days');

-- ---------------------------------------------------------------- alerts
-- All sent at the same instant (one day for v_alerts_per_user_day).
create temporary table t0 as select now() - interval '1 hour' as at;

insert into public.notifications (id, user_id, listing_id, search_profile_id, kind, channel, status, dedupe_key,
                                  payload, sent_at, opened_at, clicked_at, digested_in)
overriding system value
select v.id, v.user_id::uuid, v.listing_id, v.profile_id, v.kind::public.notification_kind,
       v.channel::public.notification_channel, v.status::public.notification_status, v.dedupe_key,
       case when v.level is null then '{}'::jsonb
            else jsonb_build_object('match', jsonb_build_object('level', v.level, 'score', v.score)) end,
       case when v.status = 'sent' then t0.at end,
       case when v.opened then t0.at end,
       case when v.clicked then t0.at end,
       v.digested_in
  from t0, (values
    -- u1: a 🔥 on Telegram (clicked) and email (not), a 🟢 unopened, a 🟡 carried by a sent digest (clicked there).
    (9600, '61111111-1111-1111-1111-111111111111', null::bigint, 9601, 'digest', 'telegram', 'sent', 'digest:2026-10-01', null::text, null::int, true,  true,  null::bigint),
    (9601, '61111111-1111-1111-1111-111111111111', 9601, 9601, 'opportunity', 'telegram', 'sent',   'match:9601', 'high',  90, true,  true,  null),
    (9602, '61111111-1111-1111-1111-111111111111', 9601, 9601, 'opportunity', 'email',    'sent',   'match:9601', 'high',  90, false, false, null),
    (9603, '61111111-1111-1111-1111-111111111111', 9602, 9601, 'new_match',   'telegram', 'sent',   'match:9602', 'good',  72, false, false, null),
    (9604, '61111111-1111-1111-1111-111111111111', 9603, 9601, 'new_match',   'telegram', 'digest', 'match:9603', 'match', 55, true,  true,  9600),
    -- u2: a 🟢 opened in the web inbox (and saved), a failed Telegram send.
    (9605, '62222222-2222-2222-2222-222222222222', 9601, 9602, 'new_match',   'web',      'sent',   'match:9601', 'good',  70, true,  false, null),
    (9606, '62222222-2222-2222-2222-222222222222', 9604, 9602, 'new_match',   'telegram', 'failed', 'match:9604', 'good',  70, false, false, null),
    -- u3: a 🟢 clicked but discarded as "automatic" (not relevant), a 🔥 clicked then discarded as too expensive (relevant).
    (9607, '63333333-3333-3333-3333-333333333333', 9602, 9603, 'new_match',   'telegram', 'sent',   'match:9602', 'good',  71, true,  true,  null),
    (9608, '63333333-3333-3333-3333-333333333333', 9604, 9603, 'opportunity', 'telegram', 'sent',   'match:9604', 'high',  88, true,  true,  null),
    -- u5: a 🟡 never opened, but the listing was opened at the source from the web.
    (9609, '65555555-5555-5555-5555-555555555555', 9603, 9605, 'new_match',   'telegram', 'sent',   'match:9603', 'match', 58, false, false, null),
    -- The admin's own alert: left out of every metric.
    (9610, '6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 9601, 9606, 'opportunity', 'telegram', 'sent',   'match:9601', 'high',  90, true,  true,  null)
  ) as v (id, user_id, listing_id, profile_id, kind, channel, status, dedupe_key, level, score, opened, clicked, digested_in);

insert into public.user_listing_interactions (user_id, listing_id, status, saved, rejection_reason) values
  ('61111111-1111-1111-1111-111111111111', 9601, 'purchased',       false, null),
  ('62222222-2222-2222-2222-222222222222', 9601, 'seen',            true,  null),
  ('63333333-3333-3333-3333-333333333333', 9602, 'discarded',       false, 'automatic'),
  ('63333333-3333-3333-3333-333333333333', 9604, 'discarded',       false, 'too_expensive'),
  ('63333333-3333-3333-3333-333333333333', 9605, 'visit_scheduled', false, null),
  ('6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 9601, 'contacted',       false, null);

insert into public.owned_vehicles (user_id, listing_id, search_profile_id, vehicle, purchase_price, purchase_currency,
                                   automotive_influence)
values ('61111111-1111-1111-1111-111111111111', 9601, 9601, '{"title": "Pgtap F6 1"}', 9800, 'USD', 'a_lot');

-- ---------------------------------------------------------------- events
insert into public.events (user_id, name, props, created_at) values
  ('61111111-1111-1111-1111-111111111111', 'search_profile_created', '{"mode": "structured"}', now() - interval '25 days'),
  ('61111111-1111-1111-1111-111111111111', 'alert_clicked', '{"notification_id": 9601}', now() - interval '2 days'),
  ('61111111-1111-1111-1111-111111111111', 'alert_clicked', '{"notification_id": 9601}', now() - interval '2 days'),
  ('61111111-1111-1111-1111-111111111111', 'alert_clicked', '{"notification_id": 9600}', now() - interval '2 days'),
  ('61111111-1111-1111-1111-111111111111', 'alert_sent',    '{"notification_id": 9601}', now() - interval '1 hour'),
  ('62222222-2222-2222-2222-222222222222', 'listing_saved', '{"listing_id": 9601}',     now() - interval '10 days'),
  ('62222222-2222-2222-2222-222222222222', 'alert_sent',    '{"notification_id": 9605}', now() - interval '1 hour'),
  ('63333333-3333-3333-3333-333333333333', 'listing_status_changed', '{"listing_id": 9605, "status": "visit_scheduled"}', now() - interval '1 day'),
  ('65555555-5555-5555-5555-555555555555', 'listing_outbound_clicked', '{"listing_id": 9603}', now() - interval '10 days'),
  ('6aaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'alert_clicked', '{"notification_id": 9610}', now() - interval '1 day');

-- u2 joins the waitlist (as u2).
set local role authenticated;
set local request.jwt.claims = '{"sub": "62222222-2222-2222-2222-222222222222", "role": "authenticated"}';
select lives_ok($$select public.join_waitlist('pass_30', 'banner')$$, 'join_waitlist');
select lives_ok($$select public.join_waitlist('pro_monthly', 'plans')$$, '... again, changing the plan');
select is((select count(*)::int from public.pro_waitlist), 1, 'one waitlist row per user');
select is((select plan from public.pro_waitlist), 'pro_monthly', '... with the last plan chosen');
select results_eq(
  $$select props->>'plan', props->>'previous_plan' from public.events where name = 'waitlist_joined' order by id$$,
  $$values ('pass_30', null), ('pro_monthly', 'pass_30')$$,
  'waitlist_joined records the plan and the previous one');
select throws_ok($$select public.join_waitlist('gold')$$, '22023', null, 'only known plans');
select throws_ok($$insert into public.pro_waitlist (user_id, plan) values ('62222222-2222-2222-2222-222222222222', 'pass_90')$$,
                 '42501', null, 'the waitlist is written only through join_waitlist');
select throws_ok($$select * from public.v_validation_criteria$$, '42501', null, 'users can''t read the metrics');
select throws_ok($$select * from public.admin_users$$, '42501', null, '... nor the admin lists');
select is((public.pro_cta_state()->>'show')::boolean, false, 'pro_cta_state: no CTA once on the waitlist');
reset role;

-- ---------------------------------------------------------------- v_validation_criteria (§53)
select results_eq(
  $$select criterion, numerator::int, denominator::int, value, threshold, met
      from public.v_validation_criteria order by ordinal$$,
  $$values
    ('usage',        4, null::int, 4.0,  3::numeric,  true),
    ('relevance',    5, 7,         71.4, 30,          true),
    ('engagement',   6, 7,         85.7, 90,          false),
    ('retention',    2, 3,         66.7, 40,          true),
    ('outcome',      2, null,      2.0,  3,           false),
    ('monetization', 2, 4,         50.0, 10,          true)$$,
  'v_validation_criteria: the six §53 criteria against their thresholds');
select is((select count(*)::int from public.v_validation_criteria), 6, 'exactly six criteria');
select is((select label from public.v_validation_criteria where criterion = 'retention'), 'Retención',
          'with a label for the admin');

-- ---------------------------------------------------------------- the building blocks
select is((select count(*)::int from public.metric_users), 5, 'metric_users: everyone but the admin');
select is((select count(*)::int from public.metric_alert_rows), 8,
          'metric_alert_rows: sent rows and digested ones; no digests, failures or admin alerts');
select is((select count(*)::int from public.metric_alerts), 7, 'metric_alerts: one per user and alert, across channels');
select is((select channels from public.metric_alerts
            where user_id = '61111111-1111-1111-1111-111111111111' and dedupe_key = 'match:9601'),
          array['email', 'telegram'], '... listing its channels');
select is((select clicked_at is not null from public.metric_alerts
            where user_id = '61111111-1111-1111-1111-111111111111' and dedupe_key = 'match:9601'),
          true, '... clicked if clicked on any of them');
select is((select via_digest from public.metric_alerts
            where user_id = '61111111-1111-1111-1111-111111111111' and dedupe_key = 'match:9603'),
          true, '... and via_digest when a digest carried it');

-- ---------------------------------------------------------------- v_north_star_weekly (§35)
select is((select sum(relevant_opens)::int from public.v_north_star_weekly), 3,
          'north star: clicked alerts, minus the ones discarded as not a match');
select is((select max(active_users)::int from public.v_north_star_weekly), 4,
          'north star: active users of the week (alerted or active)');

-- ---------------------------------------------------------------- v_activation (§36)
select results_eq(
  $$select signed_up::int, with_search::int, activation_pct, target_pct
      from public.v_activation where cohort_week is null$$,
  $$values (4, 3, 75.0, 70::numeric)$$,
  'activation: web sign-ups with a search (Telegram-only and admins out)');
select is((select count(*)::int from public.v_activation where cohort_week is not null) >= 1, true,
          '... plus one row per sign-up week');

-- ---------------------------------------------------------------- v_first_value (§36)
select is((select hours_to_first_value from public.v_first_value where search_profile_id = 9601), 24.0,
          'first value: hours to the first match of level ≥ good');
select is((select first_value_at from public.v_first_value where search_profile_id = 9602), null,
          '... none yet for a search with only 🟡');

-- ---------------------------------------------------------------- v_alert_funnel (§37)
select results_eq(
  $$select level, channel, sent::int, opened::int, clicked::int, saved::int, discarded::int
      from public.v_alert_funnel$$,
  $$values ('high',  'email',    1, 0, 0, 1, 0),
           ('high',  'telegram', 2, 2, 2, 1, 1),
           ('good',  'telegram', 2, 1, 1, 0, 1),
           ('good',  'web',      1, 1, 0, 1, 0),
           ('match', 'telegram', 2, 1, 1, 0, 0)$$,
  'alert funnel per level and channel');

-- ---------------------------------------------------------------- v_high_score_engagement (§37)
select results_eq(
  $$select segment, alerts::int, click_rate_pct, engagement_pct from public.v_high_score_engagement$$,
  $$values ('high', 2, 100.0, 100.0), ('match_good', 5, 40.0, 60.0)$$,
  'high score engagement: 🔥 against 🟢/🟡');

-- ---------------------------------------------------------------- v_alerts_per_user_day (§47)
select results_eq(
  $$select users::int, alerts, alerts_per_user, max_per_user, cap from public.v_alerts_per_user_day$$,
  $$values (4::int, 6, 1.50, 2, 10)$$,
  'alerts per user and day: immediate ones, next to the cap');

-- ---------------------------------------------------------------- v_outcomes (§38)
select results_eq(
  $$select listing_id, automotive_influence::text, days_using_automotive, came_from_alert from public.v_outcomes$$,
  $$values (9601::bigint, 'a_lot', 30, true)$$,
  'outcomes: the purchase, its influence and the time using Automotive');

-- ---------------------------------------------------------------- admin lists
select results_eq(
  $$select searches::int, enabled_searches::int, alerts_7d::int, waitlist_plan, last_activity_at is not null
      from public.admin_users where email = 'u2@f6.test'$$,
  $$values (1, 1, 1, 'pro_monthly', true)$$,
  'admin_users');
select results_eq(
  $$select matches::int, high_matches::int, alerts::int from public.admin_searches where id = 9601$$,
  $$values (3, 1, 3)$$,
  'admin_searches');
select is((select sum(matches)::int from public.admin_score_histogram where bucket = 90), 1,
          'admin_score_histogram: 10-point buckets');

-- ---------------------------------------------------------------- plan limits (§33, sección 12)
select is(public.plan_limits_for('63333333-3333-3333-3333-333333333333')->>'plan', 'free',
          'plan_limits_for: an expired Pro is free');
select is(public.plan_limits_for('65555555-5555-5555-5555-555555555555')->>'plan', 'pass',
          '... a valid Search Pass is a pass');
select is((public.plan_limits_for('65555555-5555-5555-5555-555555555555')->'limits'->>'max_profiles')::int, 10,
          '... with its own limits');

set local role authenticated;
set local request.jwt.claims = '{"sub": "63333333-3333-3333-3333-333333333333", "role": "authenticated"}';
select is(public.my_plan_limits()->>'enforced', 'false', 'my_plan_limits: the pilot doesn''t enforce');

-- A second search over the free limit: allowed, measured, and it brings the CTA.
select lives_ok($$insert into public.search_profiles (user_id, name, filters, notification_frequency)
                  values ('63333333-3333-3333-3333-333333333333', 'u3 bis', '{"make": "Pgtap", "model": "F6"}', 'daily')$$,
                'max_profiles not enforced: the search is created');
select is((select count(*)::int from public.events where name = 'plan_limit_hit' and props->>'limit' = 'max_profiles'), 1,
          '... and plan_limit_hit is recorded');
select results_eq($$select pro_cta_state()->>'show', pro_cta_state()->>'reason'$$,
                  $$values ('true', 'plan_limit')$$, 'pro_cta_state: the CTA after hitting max_profiles');

-- Immediate alerts are Pro.
select lives_ok($$update public.search_profiles set notification_frequency = 'immediate' where id = 9603$$,
                'a free search switched to immediate');
select results_eq(
  $$select notification_frequency::text from public.search_profiles where id = 9603$$,
  $$values ('immediate')$$, '... stays immediate while not enforced');
select is((select count(*)::int from public.events where name = 'plan_limit_hit' and props->>'limit' = 'immediate_alerts'), 1,
          '... and records plan_limit_hit');

-- Visible results: the web reports, the database decides and dedupes.
select is(public.record_plan_limit_hit('max_visible_results', '{"search_profile_id": 9603, "total": 80}'), false,
          'record_plan_limit_hit: not enforced');
select is(public.record_plan_limit_hit('max_visible_results', '{"search_profile_id": 9603, "total": 81}'), false,
          '... twice');
select is(public.record_plan_limit_hit('max_visible_results', '{"search_profile_id": 9603, "total": 20}'), false,
          '... under the limit');
select is((select count(*)::int from public.events where name = 'plan_limit_hit' and props->>'limit' = 'max_visible_results'), 1,
          '... one event a day per search, only over the limit');
select throws_ok($$select public.record_plan_limit_hit('max_profiles', '{}')$$, '22023', null,
                 '... only for the limits the web sees');

-- u1: two distinct alerts clicked (one twice) is not "real activity" yet; a third is.
set local request.jwt.claims = '{"sub": "61111111-1111-1111-1111-111111111111", "role": "authenticated"}';
select is(public.pro_cta_state()->>'show', 'false', 'pro_cta_state: 2 alerts clicked, no CTA');
reset role;
insert into public.events (user_id, name, props)
values ('61111111-1111-1111-1111-111111111111', 'alert_clicked', '{"notification_id": 9603}');
set local role authenticated;
set local request.jwt.claims = '{"sub": "61111111-1111-1111-1111-111111111111", "role": "authenticated"}';
select results_eq($$select pro_cta_state()->>'show', pro_cta_state()->>'reason'$$,
                  $$values ('true', 'activity')$$, '... 3 alerts clicked, the CTA');
reset role;

-- Enforced.
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';
set local role authenticated;
set local request.jwt.claims = '{"sub": "64444444-4444-4444-4444-444444444444", "role": "authenticated"}';
select lives_ok($$insert into public.search_profiles (id, user_id, name, filters, notification_frequency)
                  overriding system value
                  values (9604, '64444444-4444-4444-4444-444444444444', 'u4', '{"make": "Pgtap", "model": "F6"}', 'immediate')$$,
                'enforced: a free user''s first search');
select is((select notification_frequency::text from public.search_profiles where id = 9604), 'daily',
          '... asking for immediate alerts gets the daily digest');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('64444444-4444-4444-4444-444444444444', 'u4 bis', '{"make": "Pgtap", "model": "F6"}')$$,
                 'P0001', 'plan_limit_exceeded', '... and a second search is rejected');
reset role;

select * from finish();
rollback;
