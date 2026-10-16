-- Email-only accounts (migration 20261029120000_email_only_accounts.sql): the
-- flag, the account lookup, the throttle, the credential guard, the promotion
-- after an inbox proof, the billing backstop, the LLM cap and the grants.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(64);

-- lite and lite2 are marked email-only below; full is a normal unconfirmed
-- sign-up; old, search and buyer can't be marked; sso and gone own no address.
insert into auth.users (instance_id, id, aud, role, email, email_confirmed_at, is_sso_user, deleted_at, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'e1111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'lite@eo.test',   now(), false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'e2222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'full@eo.test',   null,  false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'e3333333-3333-3333-3333-333333333333', 'authenticated', 'authenticated', 'old@eo.test',    now(), false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'e4444444-4444-4444-4444-444444444444', 'authenticated', 'authenticated', 'search@eo.test', now(), false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'e5555555-5555-5555-5555-555555555555', 'authenticated', 'authenticated', 'buyer@eo.test',  now(), false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'e6666666-6666-6666-6666-666666666666', 'authenticated', 'authenticated', 'lite2@eo.test',  now(), false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'e7777777-7777-7777-7777-777777777777', 'authenticated', 'authenticated', 'sso@eo.test',    now(), true,  null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'e8888888-8888-8888-8888-888888888888', 'authenticated', 'authenticated', 'gone@eo.test',   now(), false, now(), now(), now());
update public.profiles set created_at = now() - interval '1 day' where id = 'e3333333-3333-3333-3333-333333333333';
insert into public.search_profiles (id, user_id, name, filters) overriding system value values
  (9801, 'e4444444-4444-4444-4444-444444444444', 'S', '{"make": "Pgtap", "model": "Solo"}');

-- ------------------------------------------------------------ the flag
select is((select email_only from public.profiles where id = 'e2222222-2222-2222-2222-222222222222'), false,
          'a normal sign-up is not email-only');

select lives_ok($$insert into public.billing_checkouts (user_id, offer, offer_version, amount, billing_email)
                  values ('e5555555-5555-5555-5555-555555555555', 'pass_30', 'pgtap', 1000, 'buyer@eo.test')$$,
                'billing: a full account can start a checkout');

select is(public.mark_email_only_account('e1111111-1111-1111-1111-111111111111'), true,
          'mark_email_only_account: a profile born minutes ago');
select is((select email_only from public.profiles where id = 'e1111111-1111-1111-1111-111111111111'), true,
          '... is now email-only');
select is(public.mark_email_only_account('e3333333-3333-3333-3333-333333333333'), false,
          '... refuses a profile older than 10 minutes');
select is(public.mark_email_only_account('e4444444-4444-4444-4444-444444444444'), false,
          '... refuses one with searches');
select is(public.mark_email_only_account('e5555555-5555-5555-5555-555555555555'), false,
          '... refuses one with checkouts');
select is((select count(*)::int from public.profiles
            where email_only and id in ('e3333333-3333-3333-3333-333333333333', 'e4444444-4444-4444-4444-444444444444',
                                        'e5555555-5555-5555-5555-555555555555')), 0,
          '... and leaves them as they were');
select is(public.mark_email_only_account('e6666666-6666-6666-6666-666666666666'), true, '... a second fresh one');

-- ------------------------------------------------------------ account lookup
select results_eq($$select * from public.auth_account_for_email('  LITE@Eo.Test ')$$,
                  $$values ('e1111111-1111-1111-1111-111111111111'::uuid, true, true)$$,
                  'auth_account_for_email: any case and spaces, email-only and confirmed');
select results_eq($$select * from public.auth_account_for_email('Full@EO.test')$$,
                  $$values ('e2222222-2222-2222-2222-222222222222'::uuid, false, false)$$,
                  '... a full account not confirmed yet');
select is((select count(*)::int from public.auth_account_for_email('nobody@eo.test')), 0, '... none for an unknown email');
select is((select count(*)::int from public.auth_account_for_email('sso@eo.test'))
        + (select count(*)::int from public.auth_account_for_email('gone@eo.test')), 0,
          '... SSO and deleted users own no address');

-- ------------------------------------------------------------ throttle
insert into public.auth_throttle (kind, key, created_at) values
  ('pgtap_old', 'k', now() - interval '3 days'),
  ('pgtap_window', 'k', now() - interval '2 hours');
select is(public.claim_auth_throttle('pgtap_ip', 'k1', 2, 3600), true, 'claim_auth_throttle: first attempt');
select is(public.claim_auth_throttle('pgtap_ip', 'k1', 2, 3600), true, '... second, up to the limit');
select is(public.claim_auth_throttle('pgtap_ip', 'k1', 2, 3600), false, '... third refused');
select is((select count(*)::int from public.auth_throttle where kind = 'pgtap_ip' and key = 'k1'), 2,
          '... and not counted');
select is(public.claim_auth_throttle('pgtap_ip', 'k2', 2, 3600), true, '... another key has its own count');
select is(public.claim_auth_throttle('pgtap_global', 'k1', 2, 3600), true, '... and so has another kind');
select is(public.claim_auth_throttle('pgtap_window', 'k', 1, 3600), true, '... attempts outside the window don''t count');
select is(public.claim_auth_throttle('pgtap_window', 'k', 1, 3600), false, '... the ones inside do');
select is((select count(*)::int from public.auth_throttle where kind = 'pgtap_old'), 0, '... rows older than 2 days are pruned');
select throws_ok($$select public.claim_auth_throttle('pgtap_ip', 'k1', 2, 0)$$, '22023', 'invalid_throttle',
                 '... rejects a window it can''t keep');

-- ------------------------------------------------------------ credential guard (auth.users)
select throws_ok($$update auth.users set encrypted_password = 'squatter' where id = 'e1111111-1111-1111-1111-111111111111'$$,
                 '42501', 'account_required', 'guard: no password while email-only');
select throws_ok($$update auth.users set email = 'other@eo.test' where id = 'e1111111-1111-1111-1111-111111111111'$$,
                 '42501', 'account_required', '... no email change');
select throws_ok($$update auth.users set email_change = 'other@eo.test' where id = 'e1111111-1111-1111-1111-111111111111'$$,
                 '42501', 'account_required', '... no pending email change');
select lives_ok($$update auth.users set email_change = '' where id = 'e1111111-1111-1111-1111-111111111111'$$,
                '... clearing email_change is fine');
select lives_ok($$update auth.users set last_sign_in_at = now(), recovery_token = '', email_confirmed_at = now()
                   where id = 'e1111111-1111-1111-1111-111111111111'$$,
                '... sign-ins and verifies are fine');
select lives_ok($$update auth.users set encrypted_password = encrypted_password, email = email, email_change = email_change
                   where id = 'e1111111-1111-1111-1111-111111111111'$$,
                '... and so is GoTrue rewriting the same values');
select lives_ok($$update auth.users set encrypted_password = 'chosen', email = 'full2@eo.test', email_change = 'full3@eo.test'
                   where id = 'e2222222-2222-2222-2222-222222222222'$$,
                '... a full account changes them freely');

-- ------------------------------------------------------------ promotion
insert into auth.sessions (id, user_id, created_at, updated_at) values
  ('e0000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111', now(), now()),
  ('e0000000-0000-0000-0000-000000000003', 'e1111111-1111-1111-1111-111111111111', now(), now()),
  ('e0000000-0000-0000-0000-000000000004', 'e2222222-2222-2222-2222-222222222222', now(), now());
insert into public.account_proofs (session_id, user_id, method, created_at) values
  ('e0000000-0000-0000-0000-000000000001', 'e1111111-1111-1111-1111-111111111111', 'email_link', now() - interval '2 hours'),
  ('e0000000-0000-0000-0000-000000000002', 'e1111111-1111-1111-1111-111111111111', 'email_link', now()),
  ('e0000000-0000-0000-0000-000000000004', 'e2222222-2222-2222-2222-222222222222', 'email_link', now());

select throws_ok($$select public.complete_email_only_account('e1111111-1111-1111-1111-111111111111',
                     'e0000000-0000-0000-0000-000000000003', 'password')$$,
                 '42501', 'proof_required', 'complete_email_only_account: a session without a proof');
select throws_ok($$select public.complete_email_only_account('e1111111-1111-1111-1111-111111111111',
                     'e0000000-0000-0000-0000-000000000001', 'password')$$,
                 '42501', 'proof_required', '... a proof older than an hour');
select throws_ok($$select public.complete_email_only_account('e1111111-1111-1111-1111-111111111111',
                     'e0000000-0000-0000-0000-000000000002', 'password')$$,
                 '42501', 'proof_required', '... a proof whose session is gone');
select throws_ok($$select public.complete_email_only_account('e1111111-1111-1111-1111-111111111111',
                     'e0000000-0000-0000-0000-000000000004', 'password')$$,
                 '42501', 'proof_required', '... another account''s proof');
select throws_ok($$select public.complete_email_only_account('e1111111-1111-1111-1111-111111111111',
                     'e0000000-0000-0000-0000-000000000003', 'magic')$$,
                 '22023', 'invalid_method', '... an unknown method');

insert into public.account_proofs (session_id, user_id, method) values
  ('e0000000-0000-0000-0000-000000000003', 'e1111111-1111-1111-1111-111111111111', 'email_link');
select is(public.complete_email_only_account('e1111111-1111-1111-1111-111111111111',
            'e0000000-0000-0000-0000-000000000003', 'password'), true,
          '... a fresh proof for a live session');
select is((select email_only from public.profiles where id = 'e1111111-1111-1111-1111-111111111111'), false,
          '... makes it a full account');
select is(array(select id::text from auth.sessions where user_id = 'e1111111-1111-1111-1111-111111111111'),
          array['e0000000-0000-0000-0000-000000000003'], '... and closes every other session of the account, in the same transaction');
select is(public.complete_email_only_account('e1111111-1111-1111-1111-111111111111',
            'e0000000-0000-0000-0000-000000000003', 'password'), true, '... again: harmless');
select results_eq($$select props from public.events
                     where user_id = 'e1111111-1111-1111-1111-111111111111' and name = 'account_completed'$$,
                  $$values ('{"method": "password"}'::jsonb)$$, '... one account_completed event');
select lives_ok($$update auth.users set encrypted_password = 'chosen' where id = 'e1111111-1111-1111-1111-111111111111'$$,
                '... and now the password can be set');

-- ------------------------------------------------------------ footholds left by whoever typed the email
insert into auth.mfa_factors (id, user_id, friendly_name, factor_type, status, created_at, updated_at)
values ('e0000000-0000-0000-0000-0000000000f1', 'e6666666-6666-6666-6666-666666666666', 'pgtap', 'totp', 'verified', now(), now());
update public.profiles set telegram_chat_id = 4242, telegram_user_id = 4242 where id = 'e6666666-6666-6666-6666-666666666666';
create temp table pgtap_codes as select id, telegram_link_code from public.profiles where id = 'e6666666-6666-6666-6666-666666666666';
select is(public.secure_email_only_account('e6666666-6666-6666-6666-666666666666'), true,
          'secure_email_only_account clears an email-only account');
select is((select count(*) from auth.mfa_factors where user_id = 'e6666666-6666-6666-6666-666666666666'), 0::bigint,
          '... its MFA factors');
select ok((select telegram_chat_id is null and telegram_user_id is null
                  and telegram_link_code <> (select telegram_link_code from pgtap_codes)
             from public.profiles where id = 'e6666666-6666-6666-6666-666666666666'),
          '... and its Telegram link (with a new code)');
select is(public.secure_email_only_account('e2222222-2222-2222-2222-222222222222'), false,
          '... and leaves full accounts alone');

-- ------------------------------------------------------------ billing backstop
select throws_ok($$insert into public.billing_checkouts (user_id, offer, offer_version, amount, billing_email)
                   values ('e6666666-6666-6666-6666-666666666666', 'pass_30', 'pgtap', 1000, 'lite2@eo.test')$$,
                 '42501', 'account_required', 'billing: an email-only account can''t start a checkout');
select throws_ok($$update public.billing_checkouts set user_id = 'e6666666-6666-6666-6666-666666666666'
                    where user_id = 'e5555555-5555-5555-5555-555555555555'$$,
                 '42501', 'account_required', '... nor receive one');

-- ------------------------------------------------------------ LLM cap
select ok((select value ? 'email_only_per_user_hour' from public.app_config where key = 'llm_limits'),
          'llm_limits gets email_only_per_user_hour');
update public.app_config set value = '{"per_user_hour": 30}' where key = 'llm_limits';
select lives_ok($$insert into public.llm_jobs (user_id, kind, input)
                  select 'e6666666-6666-6666-6666-666666666666', 'parse_search', '{"text": "un gol trend"}'
                    from generate_series(1, 5)$$,
                'llm: an email-only account queues 5 jobs in an hour');
select throws_ok($$insert into public.llm_jobs (user_id, kind, input)
                   values ('e6666666-6666-6666-6666-666666666666', 'parse_search', '{"text": "un gol trend"}')$$,
                 'P0001', 'llm_rate_limited', '... not a 6th (default 5 without the key)');
select lives_ok($$insert into public.llm_jobs (user_id, kind, input)
                  select 'e2222222-2222-2222-2222-222222222222', 'parse_search', '{"text": "un gol trend"}'
                    from generate_series(1, 6)$$,
                '... a full account keeps per_user_hour');
update public.app_config set value = '{"per_user_hour": 30, "email_only_per_user_hour": 6}' where key = 'llm_limits';
select lives_ok($$insert into public.llm_jobs (user_id, kind, input)
                  values ('e6666666-6666-6666-6666-666666666666', 'parse_search', '{"text": "un gol trend"}')$$,
                '... and email_only_per_user_hour sets the email-only cap');

-- ------------------------------------------------------------ grants
select is(array(select r || ' ' || f
                  from unnest(array['anon', 'authenticated']) r,
                       unnest(array['public.mark_email_only_account(uuid)', 'public.auth_account_for_email(text)',
                                    'public.claim_auth_throttle(text,text,integer,integer)',
                                    'public.complete_email_only_account(uuid,uuid,text)', 'public.secure_email_only_account(uuid)',
                                    'public.guard_email_only_credentials()', 'public.guard_billing_account()',
                                    'public.enforce_llm_rate_limit()']) f
                 where has_function_privilege(r, f, 'execute')),
          '{}'::text[], 'anon and authenticated can execute none of the new functions');
select is(array(select f
                  from unnest(array['public.mark_email_only_account(uuid)', 'public.auth_account_for_email(text)',
                                    'public.claim_auth_throttle(text,text,integer,integer)',
                                    'public.complete_email_only_account(uuid,uuid,text)', 'public.secure_email_only_account(uuid)']) f
                 where not has_function_privilege('service_role', f, 'execute')),
          '{}'::text[], '... the service role can');
select is(array(select r || ' ' || t || ' ' || p
                  from unnest(array['anon', 'authenticated']) r,
                       unnest(array['public.auth_throttle', 'public.account_proofs']) t,
                       unnest(array['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p
                 where has_table_privilege(r, t, p)),
          '{}'::text[], 'anon and authenticated can''t touch auth_throttle or account_proofs');
select is(array(select relname::text from pg_class
                 where oid in ('public.auth_throttle'::regclass, 'public.account_proofs'::regclass) and not relrowsecurity),
          '{}'::text[], '... and both have RLS on');
select is(has_column_privilege('authenticated', 'public.profiles', 'email_only', 'UPDATE'), false,
          'authenticated has no UPDATE on profiles.email_only');

set local role anon;
select throws_ok($$select * from public.auth_account_for_email('lite@eo.test')$$, '42501', null,
                 'anon can''t look up accounts');
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "e6666666-6666-6666-6666-666666666666", "role": "authenticated"}';
select throws_ok($$select public.complete_email_only_account('e6666666-6666-6666-6666-666666666666',
                     'e0000000-0000-0000-0000-000000000003', 'password')$$,
                 '42501', 'permission denied for function complete_email_only_account', 'a session can''t promote itself');
select throws_ok($$update public.profiles set email_only = false where id = 'e6666666-6666-6666-6666-666666666666'$$,
                 '42501', null, '... nor clear its own flag');
reset role;

-- ------------------------------------------------------------ delete_my_account needs a live session
insert into auth.users (instance_id, id, aud, role, email, email_confirmed_at, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'e9999999-9999-9999-9999-999999999999', 'authenticated', 'authenticated', 'leaving@eo.test', now(), now(), now());
insert into auth.sessions (id, user_id, created_at, updated_at) values
  ('e0000000-0000-0000-0000-000000000009', 'e9999999-9999-9999-9999-999999999999', now(), now());
set local role authenticated;
set local request.jwt.claims = '{"sub": "e9999999-9999-9999-9999-999999999999", "role": "authenticated", "session_id": "e0000000-0000-0000-0000-0000000000aa"}';
select throws_ok($$select public.delete_my_account()$$, '42501', 'session_revoked',
                 'delete_my_account: a revoked session (its access token still valid) can''t delete the account');
set local request.jwt.claims = '{"sub": "e9999999-9999-9999-9999-999999999999", "role": "authenticated", "session_id": "e0000000-0000-0000-0000-000000000009"}';
select lives_ok($$select public.delete_my_account()$$, '... a live one can');
reset role;

-- ------------------------------------------------------------ admin_users
select ok((select reloptions @> array['security_invoker=true'] from pg_class where oid = 'public.admin_users'::regclass),
          'admin_users keeps security_invoker');
select ok((select attname = 'email_only' from pg_attribute where attrelid = 'public.admin_users'::regclass and attnum > 0
            order by attnum desc limit 1)
          and (select email_only from public.admin_users where id = 'e6666666-6666-6666-6666-666666666666'),
          '... and shows email_only, as its last column');

select * from finish();
rollback;
