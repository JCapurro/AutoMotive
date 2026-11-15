-- Camino al pago con código (migration 20261223120000_account_code_method.sql):
-- complete_email_only_account takes 'code' and marks the account passwordless;
-- 'password' and 'google' leave no mark; the guards stay the same.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(16);

-- code, pass and goog are email-only accounts, each with a live session and a
-- fresh proof; late has a live session and no proof.
insert into auth.users (instance_id, id, aud, role, email, email_confirmed_at, raw_app_meta_data, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c1111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'code@acm.test', now(), '{"provider": "email"}', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c2222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'pass@acm.test', now(), '{"provider": "email"}', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c3333333-3333-3333-3333-333333333333', 'authenticated', 'authenticated', 'goog@acm.test', now(), '{"provider": "email"}', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c4444444-4444-4444-4444-444444444444', 'authenticated', 'authenticated', 'late@acm.test', now(), null, now(), now());
select public.mark_email_only_account(id) from auth.users where email like '%@acm.test';
insert into auth.sessions (id, user_id, created_at, updated_at) values
  ('c0000000-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111', now(), now()),
  ('c0000000-0000-0000-0000-000000000011', 'c1111111-1111-1111-1111-111111111111', now(), now()),
  ('c0000000-0000-0000-0000-000000000002', 'c2222222-2222-2222-2222-222222222222', now(), now()),
  ('c0000000-0000-0000-0000-000000000003', 'c3333333-3333-3333-3333-333333333333', now(), now()),
  ('c0000000-0000-0000-0000-000000000004', 'c4444444-4444-4444-4444-444444444444', now(), now());
insert into public.account_proofs (session_id, user_id, method) values
  ('c0000000-0000-0000-0000-000000000001', 'c1111111-1111-1111-1111-111111111111', 'email_link'),
  ('c0000000-0000-0000-0000-000000000002', 'c2222222-2222-2222-2222-222222222222', 'email_link'),
  ('c0000000-0000-0000-0000-000000000003', 'c3333333-3333-3333-3333-333333333333', 'google');

select is((select count(*)::int from public.profiles where email_only and id in (select id from auth.users where email like '%@acm.test')), 4,
          'four email-only accounts to start with');

-- ------------------------------------------------------------ the guards
select throws_ok($$select public.complete_email_only_account('c4444444-4444-4444-4444-444444444444',
                     'c0000000-0000-0000-0000-000000000004', 'code')$$,
                 '42501', 'proof_required', 'code: a session without a proof is refused');
select is((select email_only from public.profiles where id = 'c4444444-4444-4444-4444-444444444444'), true,
          '... and stays email-only');
select is((select raw_app_meta_data ? 'passwordless' from auth.users where id = 'c4444444-4444-4444-4444-444444444444'), null,
          '... with no mark');
select throws_ok($$select public.complete_email_only_account('c1111111-1111-1111-1111-111111111111',
                     'c0000000-0000-0000-0000-000000000001', 'magic')$$,
                 '22023', 'invalid_method', 'an unknown method is refused');
select throws_ok($$select public.complete_email_only_account('c1111111-1111-1111-1111-111111111111',
                     'c0000000-0000-0000-0000-000000000001', null)$$,
                 '22023', 'invalid_method', '... and so is none');

-- ------------------------------------------------------------ 'code'
select is(public.complete_email_only_account('c1111111-1111-1111-1111-111111111111',
            'c0000000-0000-0000-0000-000000000001', 'code'), true,
          'code: a fresh proof for a live session completes the account');
select is((select email_only from public.profiles where id = 'c1111111-1111-1111-1111-111111111111'), false,
          '... which is a full account now');
select is((select raw_app_meta_data from auth.users where id = 'c1111111-1111-1111-1111-111111111111'),
          '{"provider": "email", "passwordless": true}'::jsonb,
          '... marked passwordless, keeping the rest of app_metadata');
select is(array(select id::text from auth.sessions where user_id = 'c1111111-1111-1111-1111-111111111111'),
          array['c0000000-0000-0000-0000-000000000001'], '... and every other session is closed');
select is(public.complete_email_only_account('c1111111-1111-1111-1111-111111111111',
            'c0000000-0000-0000-0000-000000000001', 'code'), true, '... again: harmless');
select results_eq($$select props from public.events
                     where user_id = 'c1111111-1111-1111-1111-111111111111' and name = 'account_completed'$$,
                  $$values ('{"method": "code"}'::jsonb)$$, '... one account_completed { method: code }');

-- ------------------------------------------------------------ 'password' and 'google' leave no mark
select is(public.complete_email_only_account('c2222222-2222-2222-2222-222222222222',
            'c0000000-0000-0000-0000-000000000002', 'password'), true, 'password: completes the account');
select is((select raw_app_meta_data ? 'passwordless' from auth.users where id = 'c2222222-2222-2222-2222-222222222222'), false,
          '... with no passwordless mark');
select is(public.complete_email_only_account('c3333333-3333-3333-3333-333333333333',
            'c0000000-0000-0000-0000-000000000003', 'google'), true, 'google: completes the account');
select is((select raw_app_meta_data ? 'passwordless' from auth.users where id = 'c3333333-3333-3333-3333-333333333333'), false,
          '... with no passwordless mark');

select * from finish();
rollback;
