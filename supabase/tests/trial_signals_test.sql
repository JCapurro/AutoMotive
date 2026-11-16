-- Una prueba por persona (migration 20261224120000_trial_signals.sql): the
-- canonical email, the lookup of another spelling, the signals and the grants.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(16);

insert into auth.users (instance_id, id, aud, role, email, email_confirmed_at, is_sso_user, deleted_at, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'f1111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated', 'juanperez@gmail.com', now(), false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f2222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated', 'ana@hotmail.com',     null,  false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f3333333-3333-3333-3333-333333333333', 'authenticated', 'authenticated', 'luis+a@empresa.test', now(), false, null,  now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f4444444-4444-4444-4444-444444444444', 'authenticated', 'authenticated', 'gone@gmail.com',      now(), false, now(), now(), now());

-- ------------------------------------------------------------ email_canonical
select is(public.email_canonical(' Juan.Perez+2@Gmail.com '), 'juanperez@gmail.com', 'gmail: no dots, no +, any case and spaces');
select is(public.email_canonical('juanperez@googlemail.com'), 'juanperez@gmail.com', 'googlemail is gmail');
select is(public.email_canonical('ana+x@hotmail.com.ar'), 'ana@hotmail.com.ar', 'hotmail: no +');
select is(public.email_canonical('pepe.lopez@outlook.com'), 'pepe.lopez@outlook.com', 'outlook keeps its dots');
select is(public.email_canonical('ana+x@empresa.com.ar'), 'ana+x@empresa.com.ar', 'an unknown domain keeps its +');
select is(public.email_canonical(null), null, 'null stays null');

-- ------------------------------------------------------------ another spelling
select results_eq($$select user_id, email from public.auth_account_for_canonical_email('J.uan.Perez+3@googlemail.com')$$,
                  $$values ('f1111111-1111-1111-1111-111111111111'::uuid, 'juanperez@gmail.com')$$,
                  'auth_account_for_canonical_email: another spelling finds the account and its email');
select is((select count(*)::int from public.auth_account_for_canonical_email('JuanPerez@gmail.com')), 0,
          '... the exact email is not "another" spelling');
select results_eq($$select user_id, confirmed from public.auth_account_for_canonical_email('ana+promo@hotmail.com')$$,
                  $$values ('f2222222-2222-2222-2222-222222222222'::uuid, false)$$, '... hotmail +');
select is((select count(*)::int from public.auth_account_for_canonical_email('luis+b@empresa.test')), 0,
          '... + on an unknown domain is another inbox');
select is((select count(*)::int from public.auth_account_for_canonical_email('g.o.n.e@gmail.com')), 0,
          '... deleted users own no address');

-- ------------------------------------------------------------ signals
select public.record_trial_signals('f1111111-1111-1111-1111-111111111111', 'Juan.Perez@gmail.com', '0123456789abcdef0123456789abcdef', 'unknown');
select results_eq($$select email_canonical, ip_key, device_key from public.trial_signals where user_id = 'f1111111-1111-1111-1111-111111111111'$$,
                  $$values ('juanperez@gmail.com', '0123456789abcdef0123456789abcdef', null::text)$$,
                  'record_trial_signals: canonical email and IP key; a junk device key is dropped');
select public.record_trial_signals('f1111111-1111-1111-1111-111111111111', 'x@gmail.com', 'ffffffffffffffffffffffffffffffff', 'abcdefabcdefabcdefabcdefabcdefab');
select results_eq($$select ip_key, device_key from public.trial_signals where user_id = 'f1111111-1111-1111-1111-111111111111'$$,
                  $$values ('0123456789abcdef0123456789abcdef', 'abcdefabcdefabcdefabcdefabcdefab')$$,
                  '... a second call fills what was missing and keeps what was there');
select public.record_trial_signals('f9999999-9999-9999-9999-999999999999', 'x@gmail.com', null, null);
select is((select count(*)::int from public.trial_signals where user_id = 'f9999999-9999-9999-9999-999999999999'), 0,
          '... nothing for a user without a profile');

-- ------------------------------------------------------------ grants
select ok(not has_function_privilege('authenticated', 'public.auth_account_for_canonical_email(text)', 'execute')
          and not has_function_privilege('anon', 'public.record_trial_signals(uuid, text, text, text)', 'execute'),
          'grants: the functions are service role only');
select ok(not has_table_privilege('authenticated', 'public.trial_signals', 'select')
          and not has_table_privilege('anon', 'public.trial_signals', 'select'),
          '... and so is the table');

select * from finish();
rollback;
