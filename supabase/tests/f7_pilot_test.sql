-- F7 pilot (migration 20261004120000_f7_pilot.sql): email unsubscribe, account
-- deletion and retention. Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(20);

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '77777777-7777-7777-7777-777777777777',
   'authenticated', 'authenticated', 'a@f7.test', now() - interval '12 days', now()),
  ('00000000-0000-0000-0000-000000000000', '88888888-8888-8888-8888-888888888888',
   'authenticated', 'authenticated', 'b@f7.test', now(), now());
update public.profiles set created_at = now() - interval '12 days', default_channels = '{telegram,email,web}'
 where id = '77777777-7777-7777-7777-777777777777';

insert into public.search_profiles (id, user_id, name, filters, channels) overriding system value values
  (9701, '77777777-7777-7777-7777-777777777777', 'A1', '{"make": "Pgtap", "model": "Siete"}', '{telegram,email,web}'),
  (9702, '77777777-7777-7777-7777-777777777777', 'A2', '{"make": "Pgtap", "model": "Siete"}', '{email,web}'),
  (9703, '88888888-8888-8888-8888-888888888888', 'B1', '{"make": "Pgtap", "model": "Siete"}', '{email,web}');

-- Listings for the retention: old ones in every situation, and a recent one.
insert into public.listings (id, source, external_id, url, title, make, model, first_seen_at, last_seen_at, status)
overriding system value values
  (9701, 'mercadolibre', 'F7-1', 'https://example.test/f7-1', 'viejo, nadie lo tocó',    'Pgtap', 'Siete', now() - interval '300 days', now() - interval '200 days', 'active'),
  (9702, 'mercadolibre', 'F7-2', 'https://example.test/f7-2', 'viejo y gone',            'Pgtap', 'Siete', now() - interval '300 days', now() - interval '190 days', 'gone'),
  (9703, 'mercadolibre', 'F7-3', 'https://example.test/f7-3', 'viejo, guardado',         'Pgtap', 'Siete', now() - interval '300 days', now() - interval '200 days', 'gone'),
  (9704, 'mercadolibre', 'F7-4', 'https://example.test/f7-4', 'viejo, alertado',         'Pgtap', 'Siete', now() - interval '300 days', now() - interval '200 days', 'gone'),
  (9705, 'mercadolibre', 'F7-5', 'https://example.test/f7-5', 'viejo, comprado',         'Pgtap', 'Siete', now() - interval '300 days', now() - interval '200 days', 'gone'),
  (9706, 'mercadolibre', 'F7-6', 'https://example.test/f7-6', 'visto hace poco',         'Pgtap', 'Siete', now() - interval '300 days', now() - interval '10 days',  'active'),
  (9707, 'mercadolibre', 'F7-7', 'https://example.test/f7-7', 'repost de uno que se va', 'Pgtap', 'Siete', now() - interval '5 days',   now(),                       'active');
update public.listings set probable_repost_of = 9701 where id = 9707;
insert into public.listing_snapshots (listing_id, attrs_hash, change_kind) values (9701, 'x', 'new');
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (9701, 9701, 60, 'match', '{}', '{}', 'test');
insert into public.user_listing_interactions (user_id, listing_id, saved) values
  ('88888888-8888-8888-8888-888888888888', 9703, true);
insert into public.notifications (user_id, listing_id, kind, channel, dedupe_key) values
  ('88888888-8888-8888-8888-888888888888', 9704, 'new_match', 'web', 'new_match:9704');
insert into public.owned_vehicles (user_id, listing_id) values
  ('88888888-8888-8888-8888-888888888888', 9705);

-- ------------------------------------------------------------ retention
select throws_ok($$select public.purge_stale_listings(7)$$, 'P0001', null, 'retention: refuses less than 30 days');
select is(public.purge_stale_listings(), 1, 'retention: only untouched active listings unseen for 180+ days');
select results_eq($$select id from public.listings where id between 9701 and 9707 order by id$$,
                  $$values (9702::bigint), (9703::bigint), (9704::bigint), (9705::bigint), (9706::bigint), (9707::bigint)$$,
                  '... ended history, saved, alerted, bought and recent ones stay');
select is((select count(*)::int from public.listing_snapshots where listing_id = 9701), 0, '... snapshots go with it');
select is((select count(*)::int from public.matches where listing_id = 9701), 0, '... and its matches');
select is((select probable_repost_of from public.listings where id = 9707), null, '... a repost of it is unlinked');
select is(public.purge_stale_listings(), 0, 'retention: idempotent');

-- ------------------------------------------------------------ unsubscribe (anon, from an email link)
select email_unsubscribe_token as token from public.profiles
 where id = '77777777-7777-7777-7777-777777777777' \gset
set local role anon;
select is(public.unsubscribe_email(gen_random_uuid()), null, 'unsubscribe: unknown token does nothing');
reset role;
select results_eq($$select channels from public.search_profiles where id between 9701 and 9703 order by id$$,
                  $$values ('{telegram,email,web}'::text[]), ('{email,web}'::text[]), ('{email,web}'::text[])$$,
                  '... nothing changed');

set local role anon;
select is(public.unsubscribe_email(:'token'),
          'a@f7.test', 'unsubscribe: anon with the token, returns the address');
reset role;
select is((select default_channels from public.profiles where id = '77777777-7777-7777-7777-777777777777'),
          '{telegram,web}'::text[], '... email out of the defaults');
select results_eq($$select channels from public.search_profiles
                     where user_id = '77777777-7777-7777-7777-777777777777' order by id$$,
                  $$values ('{telegram,web}'::text[]), ('{web}'::text[])$$, '... and out of every search');
select is((select count(*)::int from public.search_profiles where id = 9703 and 'email' = any(channels)), 1,
          '... another user''s searches untouched');
select is((select count(*)::int from public.events where name = 'email_unsubscribed'
                                                    and user_id = '77777777-7777-7777-7777-777777777777'),
          1, '... one email_unsubscribed event');

set local role anon;
select is(public.unsubscribe_email(:'token'),
          'a@f7.test', 'unsubscribe: a second click is harmless');
reset role;
select is((select count(*)::int from public.events where name = 'email_unsubscribed'
                                                    and user_id = '77777777-7777-7777-7777-777777777777'),
          1, '... and records nothing new');

-- ------------------------------------------------------------ account deletion
set local role anon;
select throws_ok($$select public.delete_my_account()$$, '42501', null, 'delete_my_account: not for anon');
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub": "77777777-7777-7777-7777-777777777777", "role": "authenticated"}';
select lives_ok($$select public.delete_my_account()$$, 'delete_my_account: the user deletes their account');
reset role;
select is((select count(*)::int from auth.users where id = '77777777-7777-7777-7777-777777777777')
        + (select count(*)::int from public.profiles where id = '77777777-7777-7777-7777-777777777777')
        + (select count(*)::int from public.search_profiles where user_id = '77777777-7777-7777-7777-777777777777'),
          0, '... auth user, profile and searches are gone');
select is((select props from public.events where name = 'account_deleted' and user_id is null
            order by id desc limit 1),
          '{"days_since_signup": 12, "searches": 2}'::jsonb, '... one anonymous account_deleted event');

select * from finish();
rollback;
