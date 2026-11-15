-- Prospección (20261225120000_prospecting, docs/PROSPECCION.md): the cadence and
-- states of admin_prospect_action, and that no client can read the tables.
-- Run in an isolated local database; all fixtures roll back.
begin;
select plan(20);

insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at) values
('00000000-0000-0000-0000-000000000000','61616161-6161-6161-6161-616161616160','authenticated','authenticated','prosp-admin@example.test',now(),now()),
('00000000-0000-0000-0000-000000000000','61616161-6161-6161-6161-616161616161','authenticated','authenticated','prosp-user@example.test',now(),now());
update public.profiles set role = 'admin' where id = '61616161-6161-6161-6161-616161616160';

-- Business days: Friday + 5 = next Friday; Saturday + 5 = next Friday; Monday + 5 = next Monday.
select is(public.prospect_add_business_days('2026-11-13', 5), '2026-11-20'::date, 'friday + 5 business days');
select is(public.prospect_add_business_days('2026-11-14', 5), '2026-11-20'::date, 'saturday + 5 business days');
select is(public.prospect_add_business_days('2026-11-16', 5), '2026-11-23'::date, 'monday + 5 business days');

insert into public.prospects(id, prospect_key, seller_keys, kind, display_name, phone, status) overriding system value
values (961, 'test|uno', '{test|uno}', 'agencia', 'Uno', '5493415123456', 'queued');
insert into public.prospect_messages(id, prospect_id, step, batch_date, facts, variants, chosen_index, final_text, hook_type) overriding system value
values (9611, 961, 'first', current_date, '{}',
        '[{"hook_type":"oportunidad","text":"A"},{"hook_type":"stock_viejo","text":"B"}]', 0, 'A', 'oportunidad');

select throws_ok($$select public.admin_prospect_action('61616161-6161-6161-6161-616161616161', 961, 9611, 'sent', null)$$,
                 'admin_required', 'only an admin acts');

select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, 9611, 'chose_variant', '1');
select is((select final_text || '/' || hook_type from public.prospect_messages where id = 9611), 'B/stock_viejo', 'the other variant');
select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, 9611, 'edited', ' Texto de Juan ');
select is((select final_text from public.prospect_messages where id = 9611), 'Texto de Juan', 'an edit replaces the text');
select ok((select edited from public.prospect_messages where id = 9611), 'and is marked');

select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, 9611, 'sent', null);
select is((select status from public.prospects where id = 961), 'contacted', 'first message sent');
select is((select next_due_on from public.prospects where id = 961),
          public.prospect_add_business_days((now() at time zone 'America/Argentina/Buenos_Aires')::date, 5),
          'the follow-up is due 5 business days later');
select throws_ok($$select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, 9611, 'sent', null)$$,
                 'message_not_ready', 'a message is sent once');

insert into public.prospect_messages(id, prospect_id, step, batch_date, facts, final_text) overriding system value
values (9612, 961, 'followup', current_date, '{}', 'F');
select throws_ok($$insert into public.prospect_messages(prospect_id, step, batch_date, facts, final_text)
                   values (961, 'last', current_date, '{}', 'X')$$, '23505', null, 'one ready message per prospect');
select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, 9612, 'sent', null);
select is((select status || '/' || (next_due_on - (now() at time zone 'America/Argentina/Buenos_Aires')::date)
             from public.prospects where id = 961), 'followed_up/15', 'the last message is due 15 days after the follow-up');

insert into public.prospect_messages(id, prospect_id, step, batch_date, facts, final_text) overriding system value
values (9613, 961, 'last', current_date, '{}', 'L');
select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, 9613, 'sent', null);
select is((select status from public.prospects where id = 961), 'closed', 'after the last message, closed');
select is((select next_due_on from public.prospects where id = 961), null, 'with nothing due');

select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, null, 'replied', null);
select is((select status from public.prospects where id = 961), 'replied', 'a reply wins over closed');
select isnt((select replied_at from public.prospects where id = 961), null, 'with its time');

select throws_ok($$select public.admin_prospect_action('61616161-6161-6161-6161-616161616160', 961, null, 'phone_set', '341')$$,
                 'invalid_phone', 'a phone in wa.me form only');
select is((select count(*)::int from public.prospect_events where prospect_id = 961), 6, 'every action is logged');

set local role authenticated;
select throws_ok($$select 1 from public.prospects$$, '42501', null, 'a signed-in client cannot read prospects');
reset role;
set local role anon;
select throws_ok($$select 1 from public.prospect_messages$$, '42501', null, 'an anonymous client cannot read messages');
reset role;

select * from finish();
rollback;
